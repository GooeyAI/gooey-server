import json
import time
import uuid
from enum import Enum

import requests
import streamlit as st
from decouple import config
from google.cloud import texttospeech
from pydantic import BaseModel
from google.oauth2 import service_account

from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.base import DarsAiPage
credentials = service_account.Credentials.from_service_account_file('serviceAccountKey.json')


class TextToSpeechProviders(Enum):
    GOOGLE_TTS = 1
    UBERDUCK = 2


class TextToSpeechPage(DarsAiPage):
    doc_name = "TextToSpeech"
    title = "Text to Speech"
    endpoint = "/v1/TextToSpeech/run"

    class RequestModel(BaseModel):
        text_prompt: str

    class ResponseModel(BaseModel):
        audio_url: str

    def render_description(self):
        st.write(
            """
    *Convert text into audio*


    How It Works:

    1. Takes text input
    2. Generates audio file in voice of your choice
    3. Play in the browser
    """
        )

    def render_form(self):
        with st.form("my_form"):
            st.write(
                """
                ### Prompt
                Enter text you want to convert to speech
                """
            )
            st.text_area(
                "text_prompt",
                label_visibility="collapsed",
                key="text_prompt",
                placeholder="This is a test",
                value="This is a test",
            )
            st.radio(
                "Provider",
                horizontal=True,
                options=[provider.name for provider in TextToSpeechProviders],
                key="tts_provider"
            )
            col1, col2 = st.columns(2)

            with col1:
                st.text_input(label="Voice name(Google TTS)", value="en-US-Neural2-F", key="google_tts_voice_name")

            with col2:
                st.text_input(label="Voice name (Uberduck)", value="zwf", key="uberduck_voice_name")

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

    def render_output(self):
        text_prompt = st.session_state.get("text_prompt", "")
        audio_url = st.session_state.get("audio_url")
        if audio_url:
            st.audio(audio_url)

    def run(self, state: dict):
        yield "Generating Audio..."
        text = state["text_prompt"]
        tts_provider = state["tts_provider"]
        if tts_provider == TextToSpeechProviders.UBERDUCK.name:
            voice_name = state["uberduck_voice_name"]
            response = requests.post(
                "https://api.uberduck.ai/speak",
                auth=(config("UBERDUCK_KEY"), config("UBERDUCK_SECRET")),
                json={"speech": text, "voice": voice_name}
            )
            file_uuid = json.loads(response.text)["uuid"]
            while True:
                data = requests.get(f"https://api.uberduck.ai/speak-status?uuid={file_uuid}")
                path = json.loads(data.text)["path"]
                if path:
                    state["audio_url"] = path
                    break
                else:
                    time.sleep(2)

        if tts_provider == TextToSpeechProviders.GOOGLE_TTS.name:
            voice_name = state["google_tts_voice_name"]
            client = texttospeech.TextToSpeechClient(credentials=credentials)

            synthesis_input = texttospeech.SynthesisInput(text=text)
            voice = texttospeech.VoiceSelectionParams()
            voice.language_code = "en-US"
            voice.name = voice_name  # optional

            # Select the type of audio file you want returned
            audio_config = texttospeech.AudioConfig()
            audio_config.audio_encoding = texttospeech.AudioEncoding.MP3
            audio_config.pitch = 0.0  # optional
            audio_config.speaking_rate = 1.0  # optional

            # Perform the text-to-speech request on the text input with the selected
            # voice parameters and audio file type
            response = client.synthesize_speech(
                input=synthesis_input, voice=voice, audio_config=audio_config)
            yield "Uploading Audio file..."
            state["audio_url"] = upload_file_from_bytes(
                f"google_tts_{uuid.uuid4()}.mp3", response.audio_content
            )


    def render_example(self, state: dict):
        col1, col2 = st.columns(2)
        with col1:
            input_image = state.get("input_image")
            if input_image:
                st.image(input_image)
        with col2:
            output_images = state.get("output_images")
            if output_images:
                for img in output_images:
                    st.image(img)


if __name__ == "__main__":
    TextToSpeechPage().render()
