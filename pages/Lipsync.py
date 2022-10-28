import typing

import replicate
import requests
import streamlit as st
from pydantic import BaseModel

from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.base import DarsAiPage


class LipsyncPage(DarsAiPage):
    title = "Lipsync"
    doc_name = "Lipsync"
    endpoint = "/v1/Lipsync/run"

    class RequestModel(BaseModel):
        input_face: str
        input_audio: str

    class ResponseModel(BaseModel):
        output_video: str

    def render_form(self) -> bool:
        with st.form("my_form"):
            st.write(
                """
                ### Input Face
                Upload a video/image that contains faces to use
                """
            )
            face_file = st.file_uploader("input face", label_visibility="collapsed")

            st.write(
                """
                ### Input Audio
                Upload the video/audio file to use as audio source for lip syncing
                """
            )
            audio_file = st.file_uploader("input audio", label_visibility="collapsed")

            submitted = st.form_submit_button("☑️ Submit")

        # upload input files if submitted
        if submitted:
            with st.spinner("Uploading..."):
                if face_file:
                    st.session_state["input_face"] = upload_file_from_bytes(
                        face_file.name, face_file.getvalue()
                    )
                if audio_file:
                    st.session_state["input_audio"] = upload_file_from_bytes(
                        audio_file.name, audio_file.getvalue()
                    )

        return submitted

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request = self.RequestModel.parse_obj(state)

        yield "Running wav2lip..."

        model = replicate.models.get("devxpy/cog-wav2lip").versions.get(
            "37084febcf7a530c994fc607937ada9101975eba360f547b1aa1e020bf8f1317"
        )
        output = model.predict(face=request.input_face, audio=request.input_audio)

        state["output_video"] = upload_file_from_bytes(
            "output.mp4", requests.get(output).content
        )

    def render_output(self):
        col1, col2 = st.columns(2)

        with col1:
            st.write("Input Face")
            input_face = st.session_state.get("input_face")
            if input_face:
                st.video(input_face)
            else:
                st.empty()

            st.write("Input Audio")
            input_audio = st.session_state.get("input_audio")
            if input_audio:
                st.audio(input_audio)
            else:
                st.empty()

        with col2:
            st.write("Output Video")
            output_video = st.session_state.get("output_video")
            if output_video:
                st.video(output_video)
            else:
                st.empty()


if __name__ == "__main__":
    LipsyncPage().render()
