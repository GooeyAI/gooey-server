import json
import time
from enum import Enum

import requests
import streamlit as st
from google.cloud import texttospeech
from pydantic import BaseModel

from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2 import settings
from daras_ai_v2.base import BasePage


class TextToSpeechProviders(Enum):
    GOOGLE_TTS = 1
    UBERDUCK = 2


class TextToSpeechPage(BasePage):
    title = "Speak Any Text"
    slug = "TextToSpeech"

    class RequestModel(BaseModel):
        text_prompt: str

        tts_provider: str | None

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
                value="This is a test",
            )

            submitted = st.form_submit_button("🚀 Submit")

        text_prompt = st.session_state.get("text_prompt")

        # form validation
        if submitted and not text_prompt:
            st.error("Text input cannot be empty", icon="⚠️")
            return False
        return submitted

    def render_settings(self):
        st.write(
            """
            ### Voice Settings
            """
        )
        tts_provider = st.radio(
            "Provider",
            horizontal=True,
            options=[provider.name for provider in TextToSpeechProviders],
            key="tts_provider",
        )
        if tts_provider == TextToSpeechProviders.GOOGLE_TTS.name:
            st.text_input(
                label="Voice name(Google TTS)",
                value="en-US-Neural2-F",
                key="google_voice_name",
            )
            st.write(
                "Get more voice names [here](https://cloud.google.com/text-to-speech/docs/voices)"
            )
            st.slider(
                "Pitch", min_value=-20.0, max_value=20.0, value=0.0, key="google_pitch"
            )
            st.slider(
                "Speaking rate (1.0 is the normal native speed)",
                min_value=0.25,
                max_value=4.0,
                step=0.1,
                value=1.0,
                key="google_speaking_rate",
            )

        if tts_provider == TextToSpeechProviders.UBERDUCK.name:
            st.text_input(
                label="Voice name (Uberduck)",
                value="kanye-west-rap",
                key="uberduck_voice_name",
            )
            st.write(
                "Get more voice names [here](https://app.uberduck.ai/leaderboard/voice)"
            )
            st.slider(
                "Speaking rate (1.0 is the normal native speed)",
                min_value=0.5,
                max_value=3.0,
                step=0.1,
                value=1.0,
                key="uberduck_speaking_rate",
            )

    def render_footer(self):
        col1, col2 = st.columns(2)
        with col1:
            st.write(
                """
                ## How to Use This Recipe
                """
            )
            st.markdown(
                """
                <div style="position: relative; padding-bottom: 56.25%; height: 0;"><iframe src="https://www.loom.com/embed/2d853b7442874b9cbbf3f27b98594add" frameborder="0" webkitallowfullscreen mozallowfullscreen allowfullscreen style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;"></iframe></div>
                """,
                unsafe_allow_html=True,
            )

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
            voice.language_code = "en-US"
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
