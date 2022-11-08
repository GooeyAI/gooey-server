import typing

import streamlit as st
from pydantic import BaseModel

from daras_ai.image_input import upload_file_from_bytes
from pages.Lipsync import LipsyncPage
from pages.TextToSpeech import TextToSpeechPage


class LipsyncTTSPage(LipsyncPage, TextToSpeechPage):
    title = "Lip Syncing with Text to speech"
    doc_name = "LipsyncTTS"
    endpoint = "/v1/LipsyncTTS/run"

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

        return submitted

    def render_settings(self):
        LipsyncPage.render_settings(self)
        TextToSpeechPage.render_settings(self)

    def run(self, state: dict) -> typing.Iterator[str | None]:
        yield from TextToSpeechPage.run(self, state)
        # IMP: Copy output of TextToSpeechPage "audio_url" to Lipsync as "input_audio"
        state["input_audio"] = state["audio_url"]
        yield from LipsyncPage.run(self, state)

    def render_example(self, state: dict):
        LipsyncPage.render_example(self, state)

    def render_output(self):
        self.render_example(st.session_state)


if __name__ == "__main__":
    LipsyncTTSPage().render()
