import typing
from pathlib import Path
import urllib.request
import requests

from pydantic import BaseModel

import gooey_ui as st
from bots.models import Workflow
from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.base import BasePage
from daras_ai_v2.lipsync_api import wav2lip
from daras_ai_v2.lipsync_settings_widgets import lipsync_settings
from daras_ai_v2.loom_video_widget import youtube_video

CREDITS_PER_MB = 2

DEFAULT_LIPSYNC_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/7fc4d302-9402-11ee-98dc-02420a0001ca/Lip%20Sync.jpg.png"


class LipsyncPage(BasePage):
    title = "Lip Syncing"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/f33e6332-88d8-11ee-89f9-02420a000169/Lipsync%20TTS.png.png"
    workflow = Workflow.LIPSYNC
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

    def preview_image(self, state: dict) -> str | None:
        return DEFAULT_LIPSYNC_META_IMG

    def render_form_v2(self) -> bool:
        st.file_uploader(
            """
            #### Input Face
            Upload a video/image that contains faces to use  
            *Recommended - mp4 / mov / png / jpg* 
            """,
            key="input_face",
            accept=["video/*", "image/*", "application/octet-stream"],
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

        state["output_video"] = wav2lip(
            face=request.input_face,
            audio=request.input_audio,
            pads=(
                request.face_padding_top,
                request.face_padding_bottom,
                request.face_padding_left,
                request.face_padding_right,
            ),
        )

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
                st.video(output_video, autoplay=True)
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

    def get_cost_note(self) -> str | None:
        return f"{CREDITS_PER_MB} credits per MB"

    def get_raw_price(self, state: dict) -> float:
        total_bytes = 0

        input_audio = state.get("input_audio")
        if input_audio:
            r = requests.head(input_audio)
            total_bytes += float(r.headers.get("Content-length") or "1")

        input_face = state.get("input_face")
        if input_face:
            r = requests.head(input_face)
            total_bytes += float(r.headers.get("Content-length") or "1")

        total_mb = total_bytes / 1024 / 1024
        return total_mb * CREDITS_PER_MB
