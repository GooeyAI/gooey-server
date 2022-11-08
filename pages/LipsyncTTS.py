import json
import time
import typing
from pathlib import Path

import requests
import streamlit as st
from google.cloud import texttospeech
from pydantic import BaseModel

from daras_ai.image_input import upload_file_from_bytes, safe_filename
from daras_ai_v2 import settings
from daras_ai_v2.base import BasePage
from daras_ai_v2.lipsync_api import wav2lip
from pages.TextToSpeech import TextToSpeechProviders


class LipsyncPageTTS(BasePage):
    title = "Lip Syncing with Text to speech"
    doc_name = "LipsyncTTS"
    endpoint = "/v1/Lipsync/run"

    class RequestModel(BaseModel):
        input_face: str
        input_audio: str = None

        face_padding_top: int = None
        face_padding_bottom: int = None
        face_padding_left: int = None
        face_padding_right: int = None

        text_prompt: str

        tts_provider: str = None

        uberduck_voice_name: str = None
        uberduck_speaking_rate: float = None

        google_voice_name: str = None
        google_speaking_rate: float = None
        google_pitch: float = None

    class ResponseModel(BaseModel):
        output_video: str

    def render_form(self) -> bool:
        with st.form("my_form"):
            st.write(
                """
                #### Input Face
                Upload a video/image that contains faces to use
                *Recommended - mp4 / mov / png / jpg*
                """
            )
            face_file = st.file_uploader("input face", label_visibility="collapsed")

            st.write(
                """
                #### Input Text
                This generates audio for your video
                """
            )
            text_prompt = st.text_area(
                "text_prompt",
                label_visibility="collapsed",
                key="text_prompt",
                placeholder="This is a test",
                value="This is a test",
            )
            submitted = st.form_submit_button("🏃‍ Submit")

        # upload input files if submitted
        if submitted:
            if not text_prompt:
                st.error("Text input cannot be empty", icon="⚠️")
                return False
            if not face_file:
                st.error("Input face cannot be empty", icon="⚠️")
                return False
            with st.spinner("Uploading..."):
                if face_file:
                    st.session_state["input_face"] = upload_file_from_bytes(
                        face_file.name, face_file.getvalue()
                    )
                # if audio_file:
                #     st.session_state["input_audio"] = upload_file_from_bytes(
                #         audio_file.name, audio_file.getvalue()
                #     )

        return submitted

    def render_settings(self):
        st.write(
            """
        ### Face Padding
        Adjust the detected face bounding box. Often leads to improved results.
        Recommended to give at least 10 padding for the chin region.
        """
        )

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.slider(
                "Head",
                min_value=0,
                max_value=50,
                key="face_padding_top",
            )
        with col2:
            st.slider(
                "Chin",
                min_value=0,
                max_value=50,
                key="face_padding_bottom",
            )
        with col3:
            st.slider(
                "Left Cheek",
                min_value=0,
                max_value=50,
                key="face_padding_left",
            )
        with col4:
            st.slider(
                "Right Cheek",
                min_value=0,
                max_value=50,
                key="face_padding_right",
            )
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

    def run(self, state: dict) -> typing.Iterator[str | None]:
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
                    input_audio = upload_file_from_bytes(
                        "uberduck_gen.wav", requests.get(path).content
                    )
                    state["input_audio"] = input_audio
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
            state["input_audio"] = upload_file_from_bytes(
                "google_tts_gen.mp3", response.audio_content
            )

        request = self.RequestModel.parse_obj(state)
        yield "Running LipSync..."

        img_bytes = wav2lip(
            face=request.input_face,
            audio=request.input_audio,
            pads=(
                request.face_padding_top,
                request.face_padding_bottom,
                request.face_padding_left,
                request.face_padding_right,
            ),
        )

        out_filename = safe_filename(
            f"gooey.ai lipsync - {Path(request.input_face).stem}.mp4"
        )
        state["output_video"] = upload_file_from_bytes(out_filename, img_bytes)

    def render_example(self, state: dict):
        col1, col2 = st.columns(2)

        with col1:
            input_face = state.get("input_face")
            if not input_face:
                st.empty()
            elif input_face.endswith(".mp4") or input_face.endswith(".mov"):
                st.write("Input Face (Video)")
                st.video(input_face)
            else:
                st.write("Input Face (Image)")
                st.image(input_face)

            input_audio = state.get("input_audio")
            if input_audio:
                st.write("Input Audio")
                st.audio(input_audio)
            else:
                st.empty()

        with col2:
            output_video = state.get("output_video")
            if output_video:
                st.write("Output Video")
                st.video(output_video)
            else:
                st.empty()

    def render_output(self):
        self.render_example(st.session_state)


if __name__ == "__main__":
    LipsyncPageTTS().render()
