import datetime
import json
import time
import typing

import requests
import gooey_ui as st
from google.cloud import texttospeech
from pydantic import BaseModel

from bots.models import Workflow
from daras_ai.image_input import upload_file_from_bytes, storage_blob_for
from daras_ai_v2 import settings
from daras_ai_v2.base import BasePage
from daras_ai_v2.gpu_server import GpuEndpoints
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.text_to_speech_settings_widgets import (
    UBERDUCK_VOICES,
    text_to_speech_settings,
    TextToSpeechProviders,
)

DEFAULT_TTS_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/assets/cropped_tts_compare_meta_img.gif"


class TextToSpeechPage(BasePage):
    title = "Compare AI Voice Generators"
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
    }

    class RequestModel(BaseModel):
        text_prompt: str

        tts_provider: typing.Literal[
            tuple(e.name for e in TextToSpeechProviders)
        ] | None

        uberduck_voice_name: str | None
        uberduck_speaking_rate: float | None

        google_voice_name: str | None
        google_speaking_rate: float | None
        google_pitch: float | None

        bark_history_prompt: str | None

    class ResponseModel(BaseModel):
        audio_url: str

    def fallback_preivew_image(self) -> str | None:
        return DEFAULT_TTS_META_IMG

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
            ### Prompt
            Enter text you want to convert to speech
            """,
            key="text_prompt",
        )

    def validate_form_v2(self):
        assert st.session_state["text_prompt"], "Text input cannot be empty"

    def render_settings(self):
        text_to_speech_settings()

    def render_usage_guide(self):
        youtube_video("aD4N-g9qqhc")
        # loom_video("2d853b7442874b9cbbf3f27b98594add")

    def render_output(self):
        text_prompt = st.session_state.get("text_prompt", "")
        audio_url = st.session_state.get("audio_url")
        if audio_url:
            st.audio(audio_url)
        else:
            st.div()

    def run(self, state: dict):
        text = state["text_prompt"].strip()
        tts_provider = (
            state["tts_provider"]
            if "tts_provider" in state
            else TextToSpeechProviders.UBERDUCK.name
        )
        provider = TextToSpeechProviders[tts_provider]
        yield f"Generating audio using {provider.value} ..."
        match provider:
            case TextToSpeechProviders.BARK:
                blob = storage_blob_for(f"bark_tts.wav")
                r = requests.post(
                    str(GpuEndpoints.bark),
                    json={
                        "pipeline": dict(
                            upload_urls=[
                                blob.generate_signed_url(
                                    version="v4",
                                    # This URL is valid for 15 minutes
                                    expiration=datetime.timedelta(minutes=30),
                                    # Allow PUT requests using this URL.
                                    method="PUT",
                                    content_type="audio/wav",
                                ),
                            ],
                        ),
                        "inputs": dict(
                            prompt=text.split("---"),
                            # history_prompt=history_prompt,
                        ),
                    },
                )
                r.raise_for_status()
                state["audio_url"] = blob.public_url

            case TextToSpeechProviders.UBERDUCK:
                voicemodel_uuid = (
                    UBERDUCK_VOICES.get(
                        state.get("uberduck_voice_name"), UBERDUCK_VOICES["Aiden Botha"]
                    ).strip()
                    if "uberduck_voice_name" in state
                    else UBERDUCK_VOICES["Aiden Botha"]
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
                response.raise_for_status()
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

                synthesis_input = texttospeech.SynthesisInput(text=text)

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
