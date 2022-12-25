import json
import time

import requests
import streamlit as st
import typing
from google.cloud import texttospeech
from pydantic import BaseModel

from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2 import settings
from daras_ai_v2.base import BasePage
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.text_to_speech_settings_widgets import (
    text_to_speech_settings,
    TextToSpeechProviders,
)


class TextToSpeechPage(BasePage):
    title = "Speak Any Text"
    slug = "TextToSpeech"

    sane_defaults = {
        "tts_provider": TextToSpeechProviders.GOOGLE_TTS.value,
        "google_voice_name": "en-IN-Wavenet-A",
        "google_pitch": 0.0,
        "google_speaking_rate": 1.0,
        "uberduck_voice_name": "kanye-west-rap",
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

    class ResponseModel(BaseModel):
        audio_url: str

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

    def render_form(self):
        with st.form("my_form"):
            st.text_area(
                """
                ### Prompt
                Enter text you want to convert to speech
                """,
                key="text_prompt",
                placeholder="This is a test",
            )

            submitted = st.form_submit_button("🚀 Submit")

        text_prompt = st.session_state.get("text_prompt")

        # form validation
        if submitted and not text_prompt:
            st.error("Text input cannot be empty", icon="⚠️")
            return False
        return submitted

    def render_settings(self):
        text_to_speech_settings()

    def render_usage_guide(self):
        youtube_video("pZ9ldun8aXo")
        # loom_video("2d853b7442874b9cbbf3f27b98594add")

    def render_output(self):
        text_prompt = st.session_state.get("text_prompt", "")
        audio_url = st.session_state.get("audio_url")
        if audio_url:
            st.audio(audio_url)
        else:
            st.empty()

    def run(self, state: dict):
        yield "Generating Audio..."
        text = state["text_prompt"]
        tts_provider = (
            state["tts_provider"]
            if "tts_provider" in state
            else TextToSpeechProviders.UBERDUCK.name
        )
        if tts_provider == TextToSpeechProviders.UBERDUCK.name:
            voice_name = (
                state["uberduck_voice_name"]
                if "uberduck_voice_name" in state
                else "kanye-west-rap"
            )
            pace = (
                state["uberduck_speaking_rate"]
                if "uberduck_speaking_rate" in state
                else 1.0
            )

            response = requests.post(
                "https://api.uberduck.ai/speak",
                auth=(settings.UBERDUCK_KEY, settings.UBERDUCK_SECRET),
                json={
                    "speech": text,
                    "voice": voice_name,
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

        if tts_provider == TextToSpeechProviders.GOOGLE_TTS.name:
            voice_name = (
                state["google_voice_name"]
                if "google_voice_name" in state
                else "en-US-Neural2-F"
            )
            pitch = state["google_pitch"] if "google_pitch" in state else 0.0
            speaking_rate = (
                state["google_speaking_rate"]
                if "google_speaking_rate" in state
                else 1.0
            )

            client = texttospeech.TextToSpeechClient(
                credentials=settings.google_service_account_credentials
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
            response = client.synthesize_speech(
                input=synthesis_input, voice=voice, audio_config=audio_config
            )
            yield "Uploading Audio file..."
            state["audio_url"] = upload_file_from_bytes(
                "google_tts_gen.mp3", response.audio_content
            )

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


if __name__ == "__main__":
    TextToSpeechPage().render()
