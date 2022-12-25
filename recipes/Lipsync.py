import typing
from pathlib import Path

import streamlit as st
from pydantic import BaseModel

from daras_ai.image_input import upload_file_from_bytes, safe_filename
from daras_ai_v2.base import BasePage
from daras_ai_v2.lipsync_api import wav2lip
from daras_ai_v2.lipsync_settings_widgets import lipsync_settings
from daras_ai_v2.loom_video_widget import youtube_video


class LipsyncPage(BasePage):
    title = "Lip Syncing"
    slug = "Lipsync"

    class RequestModel(BaseModel):
        input_face: str
        input_audio: str

        face_padding_top: int | None
        face_padding_bottom: int | None
        face_padding_left: int | None
        face_padding_right: int | None

    class ResponseModel(BaseModel):
        output_video: str

    def render_form(self) -> bool:
        with st.form("my_form"):
            face_file = st.file_uploader(
                """
                #### Input Face
                Upload a video/image that contains faces to use  
                *Recommended - mp4 / mov / png / jpg* 
                """,
            )

            audio_file = st.file_uploader(
                """
                #### Input Audio
                Upload the video/audio file to use as audio source for lipsyncing  
                *Recommended - wav / mp3*
                """,
            )

            submitted = st.form_submit_button("🏃‍ Submit")

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
        lipsync_settings()

    def run(self, state: dict) -> typing.Iterator[str | None]:
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

        yield "Uploading Video..."

        out_filename = f"gooey.ai lipsync - {Path(request.input_face).stem}.mp4"
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

    def render_usage_guide(self):
        youtube_video("J87EtK7ZVz0")


if __name__ == "__main__":
    LipsyncPage().render()
