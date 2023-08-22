import typing
from pathlib import Path
import urllib.request
import requests

from pydantic import BaseModel

import gooey_ui as st
from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.base import BasePage
from daras_ai_v2.lipsync_api import wav2lip
from daras_ai_v2.lipsync_settings_widgets import lipsync_settings
from daras_ai_v2.loom_video_widget import youtube_video

CREDITS_PER_BYTE = (0.000002)


class LipsyncPage(BasePage):
    title = "Lip Syncing"
    slug_versions = ["Lipsync"]

    class RequestModel(BaseModel):
        input_face: str
        input_audio: str

        face_padding_top: int | None
        face_padding_bottom: int | None
        face_padding_left: int | None
        face_padding_right: int | None

    class ResponseModel(BaseModel):
        output_video: str

    def render_form_v2(self) -> bool:
        st.file_uploader(
            """
            #### Input Face
            Upload a video/image that contains faces to use  
            *Recommended - mp4 / mov / png / jpg* 
            """,
            key="input_face",
        )

        st.file_uploader(
            """
            #### Input Audio
            Upload the video/audio file to use as audio source for lipsyncing  
            *Recommended - wav / mp3*
            """,
            key="input_audio",
        )

    def validate_form_v2(self):
        assert st.session_state.get("input_audio"), "Please provide an Audio file"
        assert st.session_state.get("input_face"), "Please provide an Input Face"

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
                st.div()
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
                st.div()

        with col2:
            output_video = state.get("output_video")
            if output_video:
                st.write("Output Video")
                st.video(output_video)
            else:
                st.div()

    def render_output(self):
        self.render_example(st.session_state)

    def related_workflows(self) -> list:
        from recipes.DeforumSD import DeforumSDPage
        from recipes.LipsyncTTS import LipsyncTTSPage
        from recipes.asr import AsrPage
        from recipes.VideoBots import VideoBotsPage

        return [DeforumSDPage, LipsyncTTSPage, AsrPage, VideoBotsPage]

    def render_usage_guide(self):
        youtube_video("EJdtC0USujM")

    def preview_description(self, state: dict) -> str:
        return "Create high-quality, realistic Lipsync animations from any audio file. Input a sample face gif/video + audio and we will automatically generate a lipsync animation that matches your audio."

    def additional_notes(self) -> str | None:
        return f"""
        *Cost ≈ {CREDITS_PER_BYTE * 1000000} credits per megabyte*
        """

    def get_raw_price(self, state: dict) -> float:
        # Retrieve the input_audio and input_face from the state dictionary
        input_audio_file_path = state.get("input_audio")
        input_face_file_path = state.get("input_face")

        audio_size_headers = requests.head(input_audio_file_path)
        audio_size = float(audio_size_headers.headers["Content-length"])

        face_size_headers = requests.head(input_face_file_path)
        face_size = float(face_size_headers.headers["Content-length"])

        if audio_size is None:
            return 0.0

        if face_size is None:
            return 0.0

        return (audio_size + face_size) * CREDITS_PER_BYTE
