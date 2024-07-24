import json
import time
import typing

import requests
from pydantic import BaseModel, Field

import gooey_ui as st
from bots.models import Workflow
from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2 import settings
from daras_ai_v2.base import BasePage
from daras_ai_v2.exceptions import raise_for_status, UserError
from daras_ai_v2.gpu_server import call_celery_task_outfile
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.pydantic_validation import FieldHttpUrl
from daras_ai_v2.text_to_speech_settings_widgets import (
    UBERDUCK_VOICES,
    ELEVEN_LABS_MODELS,
    text_to_speech_settings,
    TextToSpeechProviders,
    text_to_speech_provider_selector,
    azure_tts_voices,
    OpenAI_TTS_Models,
    OpenAI_TTS_Voices,
    OLD_ELEVEN_LABS_VOICES,
)

DEFAULT_TTS_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/a73181ce-9457-11ee-8edd-02420a0001c7/Voice%20generators.jpg.png"


class TextToSpeechSettings(BaseModel):
    tts_provider: typing.Literal[tuple(e.name for e in TextToSpeechProviders)] | None

    uberduck_voice_name: str | None
    uberduck_speaking_rate: float | None

    google_voice_name: str | None
    google_speaking_rate: float | None
    google_pitch: float | None

    bark_history_prompt: str | None

    elevenlabs_voice_name: str | None = Field(
        deprecated=True, description="Use `elevenlabs_voice_id` instead"
    )
    elevenlabs_api_key: str | None
    elevenlabs_voice_id: str | None
    elevenlabs_model: str | None
    elevenlabs_stability: float | None
    elevenlabs_similarity_boost: float | None
    elevenlabs_style: float | None = Field(0)
    elevenlabs_speaker_boost: bool | None

    azure_voice_name: str | None

    openai_voice_name: OpenAI_TTS_Voices.api_choices | None
    openai_tts_model: OpenAI_TTS_Models.api_choices | None


class TextToSpeechPage(BasePage):
    title = "Compare AI Voice Generators"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/3621e11a-88d9-11ee-b549-02420a000167/Compare%20AI%20voice%20generators.png.png"
    workflow = Workflow.TEXT_TO_SPEECH
    slug_versions = [
        "TextToSpeech",
        "tts",
        "text2speech",
        "compare-text-to-speech-engines",
    ]

    sane_defaults = {
        "tts_provider": TextToSpeechProviders.GOOGLE_TTS.value,
        "google_voice_name": "en-IN-Wavenet-A",
        "google_pitch": 0.0,
        "google_speaking_rate": 1.0,
        "uberduck_voice_name": "Aiden Botha",
        "uberduck_speaking_rate": 1.0,
        "elevenlabs_model": "eleven_multilingual_v2",
        "elevenlabs_stability": 0.5,
        "elevenlabs_similarity_boost": 0.75,
    }

    class RequestModelBase(BasePage.RequestModel):
        text_prompt: str

    class RequestModel(TextToSpeechSettings, RequestModelBase):
        pass

    class ResponseModel(BaseModel):
        audio_url: FieldHttpUrl

    def fallback_preivew_image(self) -> str | None:
        return DEFAULT_TTS_META_IMG

    @classmethod
    def get_example_preferred_fields(cls, state: dict) -> list[str]:
        return ["tts_provider"]

    def fields_not_to_save(self):
        return ["elevenlabs_api_key"]

    def fields_to_save(self):
        fields = super().fields_to_save()
        try:
            fields.remove("elevenlabs_api_key")
        except ValueError:
            pass
        return fields

    def preview_description(self, state: dict) -> str:
        return "Input your text, pick a voice & a Text-to-Speech AI engine to create audio. Compare the best voice generators from Google, UberDuck.ai & more to add automated voices to your podcast, YouTube videos, website, or app."

    def render_description(self):
        st.write(
            """
            *Convert text into audio in the voice of your choice*

            How It Works:

            1. Takes any text input
            2. Generates an audio file in voice of your choice (from Settings)
            3. Creates an audio file
            """
        )

    def render_form_v2(self):
        st.text_area(
            """
            #### Prompt
            Enter text you want to convert to speech
            """,
            key="text_prompt",
        )
        text_to_speech_provider_selector(self)

    def validate_form_v2(self):
        assert st.session_state.get("text_prompt"), "Text input cannot be empty"
        assert st.session_state.get("tts_provider"), "Please select a TTS provider"

    def render_settings(self):
        text_to_speech_settings(self, st.session_state.get("tts_provider"))

    def get_raw_price(self, state: dict):
        tts_provider = self._get_tts_provider(state)
        match tts_provider:
            case TextToSpeechProviders.ELEVEN_LABS:
                return self._get_elevenlabs_price(state)
            case _:
                return super().get_raw_price(state)

    def render_usage_guide(self):
        youtube_video("aD4N-g9qqhc")
        # loom_video("2d853b7442874b9cbbf3f27b98594add")

    def render_output(self):
        audio_url = st.session_state.get("audio_url")
        st.audio(audio_url, show_download_button=True)

    def _get_elevenlabs_price(self, state: dict):
        _, is_user_provided_key = self._get_elevenlabs_api_key(state)
        if is_user_provided_key:
            return 0
        else:
            text = state.get("text_prompt", "")
            # 0.079 credits / character ~ 4 credits / 10 words
            return len(text) * 0.079

    def _get_tts_provider(self, state: dict):
        tts_provider = state.get("tts_provider", TextToSpeechProviders.UBERDUCK.name)
        # TODO: validate tts_provider before lookup?
        return TextToSpeechProviders[tts_provider]

    def get_cost_note(self):
        tts_provider = st.session_state.get("tts_provider")
        if tts_provider == TextToSpeechProviders.ELEVEN_LABS.name:
            _, is_user_provided_key = self._get_elevenlabs_api_key(st.session_state)
            if is_user_provided_key:
                return "*No additional credit charge given we'll use your API key*"
            else:
                return "*4 credits per 10 words*"
        else:
            return ""

    def run(self, state: dict):
        text = state["text_prompt"].strip()
        provider = self._get_tts_provider(state)
        yield f"Generating audio using {provider.value} ..."
        match provider:
            case TextToSpeechProviders.BARK:
                state["audio_url"] = call_celery_task_outfile(
                    "bark",
                    pipeline=dict(
                        model_id="bark",
                    ),
                    inputs=dict(
                        prompt=text.split("---"),
                        # history_prompt=history_prompt,
                    ),
                    filename="bark_tts.wav",
                    content_type="audio/wav",
                )[0]

            case TextToSpeechProviders.UBERDUCK:
                voicemodel_uuid = (
                    UBERDUCK_VOICES.get(state.get("uberduck_voice_name"))
                    or UBERDUCK_VOICES["Aiden Botha"]
                ).strip()

                pace = (
                    state["uberduck_speaking_rate"]
                    if "uberduck_speaking_rate" in state
                    else 1.0
                )
                response = requests.post(
                    "https://api.uberduck.ai/speak",
                    auth=(settings.UBERDUCK_KEY, settings.UBERDUCK_SECRET),
                    json={
                        "voicemodel_uuid": voicemodel_uuid,
                        "speech": text,
                        "pace": pace,
                    },
                )
                raise_for_status(response)
                file_uuid = json.loads(response.text)["uuid"]
                while True:
                    data = requests.get(
                        f"https://api.uberduck.ai/speak-status?uuid={file_uuid}"
                    )
                    path = json.loads(data.text)["path"]
                    if path:
                        yield "Uploading Audio file..."
                        audio_url = upload_file_from_bytes(
                            "uberduck_gen.wav", requests.get(path).content
                        )
                        state["audio_url"] = audio_url
                        break
                    else:
                        time.sleep(0.1)

            case TextToSpeechProviders.GOOGLE_TTS:
                from google.cloud import texttospeech
                import emoji

                voice_name = (
                    state["google_voice_name"]
                    if "google_voice_name" in state
                    else "en-US-Neural2-F"
                ).strip()
                pitch = state["google_pitch"] if "google_pitch" in state else 0.0
                speaking_rate = (
                    state["google_speaking_rate"]
                    if "google_speaking_rate" in state
                    else 1.0
                )

                synthesis_input = texttospeech.SynthesisInput(
                    text=emoji.replace_emoji(text)
                )

                voice = texttospeech.VoiceSelectionParams()
                voice.language_code = "-".join(voice_name.split("-")[:2])
                voice.name = voice_name  # optional

                # Select the type of audio file you want returned
                audio_config = texttospeech.AudioConfig()
                audio_config.audio_encoding = texttospeech.AudioEncoding.MP3
                audio_config.pitch = pitch  # optional
                audio_config.speaking_rate = speaking_rate  # optional

                # Perform the text-to-speech request on the text input with the selected
                # voice parameters and audio file type
                client = texttospeech.TextToSpeechClient()
                response = client.synthesize_speech(
                    input=synthesis_input, voice=voice, audio_config=audio_config
                )

                yield "Uploading Audio file..."
                state["audio_url"] = upload_file_from_bytes(
                    f"google_tts_gen.mp3", response.audio_content
                )

            case TextToSpeechProviders.ELEVEN_LABS:
                xi_api_key, is_custom_key = self._get_elevenlabs_api_key(state)
                if not (
                    is_custom_key
                    or self.is_current_user_paying()
                    or self.is_current_user_admin()
                ):
                    raise UserError(
                        """
                        Please purchase Gooey.AI credits to use ElevenLabs voices <a href="/account">here</a>.
                        """
                    )

                voice_model = self._get_elevenlabs_voice_model(state)
                voice_id = self._get_elevenlabs_voice_id(state)

                stability = state.get("elevenlabs_stability") or 0.5
                similarity_boost = state.get("elevenlabs_similarity_boost") or 0.75
                voice_settings = dict(
                    stability=stability, similarity_boost=similarity_boost
                )
                if voice_model == "eleven_multilingual_v2":
                    voice_settings["style"] = state.get("elevenlabs_style") or 0
                    voice_settings["speaker_boost"] = state.get(
                        "elevenlabs_speaker_boost", True
                    )

                response = requests.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                    headers={
                        "xi-api-key": xi_api_key,
                        "Accept": "audio/mpeg",
                    },
                    json={
                        "text": text,
                        "model_id": voice_model,
                        "voice_settings": voice_settings,
                    },
                )
                if response.status_code == 400 and '"voice_not_found"' in response.text:
                    raise UserError(
                        f"ElevenLabs Voice {voice_id} not found. If you're trying to use a custom voice, please provide your elevenlabs_api_key."
                    )
                raise_for_status(response)

                yield "Uploading Audio file..."
                state["audio_url"] = upload_file_from_bytes(
                    "elevenlabs_gen.mp3", response.content
                )

            case TextToSpeechProviders.AZURE_TTS:
                import emoji
                import azure.cognitiveservices.speech as speechsdk

                voice_name = state.get("azure_voice_name", "en-US")
                try:
                    voice = azure_tts_voices()[voice_name]["ShortName"]
                except KeyError as e:
                    raise UserError(f"Invalid Azure voice name: {voice_name}") from e

                config = speechsdk.SpeechConfig(
                    subscription=settings.AZURE_SPEECH_KEY,
                    region=settings.AZURE_SPEECH_REGION,
                )
                config.set_speech_synthesis_output_format(
                    speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3
                )
                config.speech_synthesis_voice_name = voice
                speech_synthesizer = speechsdk.SpeechSynthesizer(config)
                result = speech_synthesizer.speak_text(emoji.replace_emoji(text))
                if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
                    raise ValueError(
                        f"Azure TTS failed: (code: {result.reason}) {result.cancellation_details.error_details}"
                    )
                stream = speechsdk.AudioDataStream(result)
                ret = bytes()
                while True:
                    buf = bytes(16_000)
                    n = stream.read_data(buf)
                    if n <= 0:
                        break
                    ret += buf[:n]
                if not ret:
                    raise ValueError(
                        f"No audio data received from azure TTS (code: {result.reason})"
                    )

                state["audio_url"] = upload_file_from_bytes(
                    "azure_tts.mp3", ret, "audio/mpeg"
                )

            case TextToSpeechProviders.OPEN_AI:
                from openai import OpenAI

                client = OpenAI()

                model = OpenAI_TTS_Models[
                    st.session_state.get(
                        "openai_tts_model", OpenAI_TTS_Models.tts_1.name
                    )
                ].value
                voice = OpenAI_TTS_Voices[
                    st.session_state.get(
                        "openai_voice_name", OpenAI_TTS_Voices.alloy.name
                    )
                ].value

                response = client.audio.speech.create(
                    model=model,
                    voice=voice,
                    input=text.strip(),
                )

                state["audio_url"] = upload_file_from_bytes(
                    "openai_tts.mp3", response.content
                )

    def _get_elevenlabs_voice_model(self, state: dict[str, str]):
        default_voice_model = next(iter(ELEVEN_LABS_MODELS))
        voice_model = state.get("elevenlabs_model", default_voice_model)
        assert voice_model in ELEVEN_LABS_MODELS, f"Invalid model: {voice_model}"
        return voice_model

    def _get_elevenlabs_voice_id(self, state: dict[str, str]) -> str:
        if voice_id := state.get("elevenlabs_voice_id"):
            return voice_id

        # default to first in the mapping
        default_voice_name = next(iter(OLD_ELEVEN_LABS_VOICES))
        voice_name = state.get("elevenlabs_voice_name", default_voice_name)
        assert voice_name in OLD_ELEVEN_LABS_VOICES, f"Invalid voice_name: {voice_name}"
        return OLD_ELEVEN_LABS_VOICES[voice_name]  # voice_name -> voice_id

    def _get_elevenlabs_api_key(self, state: dict[str, str]) -> tuple[str, bool]:
        """
        Returns the 11labs API key and whether it is a user-provided key or the default key
        """
        # ElevenLabs is available for non-paying users with their own API key
        if state.get("elevenlabs_api_key"):
            return state["elevenlabs_api_key"], True
        else:
            return settings.ELEVEN_LABS_API_KEY, False

    def related_workflows(self) -> list:
        from recipes.VideoBots import VideoBotsPage
        from recipes.LipsyncTTS import LipsyncTTSPage
        from recipes.DeforumSD import DeforumSDPage
        from recipes.CompareText2Img import CompareText2ImgPage

        return [
            VideoBotsPage,
            LipsyncTTSPage,
            DeforumSDPage,
            CompareText2ImgPage,
        ]

    def render_example(self, state: dict):
        col1, col2 = st.columns(2)
        with col1:
            text = state.get("text_prompt")
            if text:
                st.write(text)
        with col2:
            audio_url = state.get("audio_url")
            if audio_url:
                st.audio(audio_url)
