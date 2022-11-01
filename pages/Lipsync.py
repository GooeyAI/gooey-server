import typing

import replicate
import requests
import streamlit as st
from pydantic import BaseModel

from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.base import DarasAiPage


class LipsyncPage(DarasAiPage):
    title = "Lipsync"
    doc_name = "Lipsync"
    endpoint = "/v1/Lipsync/run"

    class RequestModel(BaseModel):
        input_face: str
        input_audio: str

        face_padding_top: int = None
        face_padding_bottom: int = None
        face_padding_left: int = None
        face_padding_right: int = None

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
                #### Input Audio
                Upload the video/audio file to use as audio source for lipsyncing  
                *Recommended - wav / mp3*
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

    def render_settings(self):
        st.write(
            """
        ### Face Padding
        Adjust the detected face bounding box. Often leads to improved results.  
        Recommended to give atleast 10 padding for the chin region. 
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

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request = self.RequestModel.parse_obj(state)

        yield "Running wav2lip..."

        model = replicate.models.get("devxpy/cog-wav2lip").versions.get(
            "8d65e3f4f4298520e079198b493c25adfc43c058ffec924f2aefc8010ed25eef"
        )
        output = model.predict(
            face=request.input_face,
            audio=request.input_audio,
            pads=f"{request.face_padding_top} {request.face_padding_bottom} {request.face_padding_left} {request.face_padding_right}",
        )

        yield "Downloading results..."

        state["output_video"] = upload_file_from_bytes(
            "output.mp4", requests.get(output).content
        )

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
    LipsyncPage().render()
