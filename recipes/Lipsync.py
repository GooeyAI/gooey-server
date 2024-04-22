import typing

import requests
from pydantic import BaseModel, HttpUrl

import gooey_ui as st
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.lipsync_api import wav2lip, sadtalker, SadtalkerInput
from daras_ai_v2.lipsync_settings_widgets import lipsync_settings, LipsyncModel
from daras_ai_v2.loom_video_widget import youtube_video

CREDITS_PER_MB = 2

DEFAULT_LIPSYNC_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/7fc4d302-9402-11ee-98dc-02420a0001ca/Lip%20Sync.jpg.png"


class LipsyncPage(BasePage):
    title = "Lip Syncing"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/f33e6332-88d8-11ee-89f9-02420a000169/Lipsync%20TTS.png.png"
    workflow = Workflow.LIPSYNC
    slug_versions = ["Lipsync"]

    class RequestModel(BaseModel):
        lipsync_model: str

        input_face: HttpUrl
        input_audio: HttpUrl

        # wav2lip settings
        face_padding_top: int | None
        face_padding_bottom: int | None
        face_padding_left: int | None
        face_padding_right: int | None

        # sadtalker settings
        pose_style: int = 0
        ref_eyeblink: HttpUrl | None = None
        ref_pose: HttpUrl | None = None
        batch_size: int = 2
        size: int = 256
        expression_scale: float = 1.0
        input_yaw: list[int] | None = None
        input_pitch: list[int] | None = None
        input_roll: list[int] | None = None
        enhancer: typing.Literal["gfpgan", "RestoreFormer"] | None = None
        background_enhancer: typing.Literal["realesrgan"] | None = None
        face3dvis: bool = False
        still: bool = False
        preprocess: typing.Literal["crop", "extcrop", "resize", "full", "extfull"] = (
            "crop"
        )

    class ResponseModel(BaseModel):
        output_video: str

    def preview_image(self, state: dict) -> str | None:
        return DEFAULT_LIPSYNC_META_IMG

    def render_form_v2(self):
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

        if request.lipsync_model == LipsyncModel.Wav2Lip.name:
            yield "Running Wav2Lip..."
            state["output_video"] = wav2lip(
                face=request.input_face,
                audio=request.input_audio,
                pads=(
                    request.face_padding_top or 0,
                    request.face_padding_bottom or 0,
                    request.face_padding_left or 0,
                    request.face_padding_right or 0,
                ),
            )
        elif request.lipsync_model == LipsyncModel.SadTalker.name:
            yield "Running SadTalker..."
            state["output_video"] = sadtalker(
                SadtalkerInput(
                    source_image=request.input_face,
                    driven_audio=request.input_audio,
                    pose_style=request.pose_style,
                    ref_eyeblink=request.ref_eyeblink,
                    ref_pose=request.ref_pose,
                    batch_size=request.batch_size,
                    size=request.size,
                    expression_scale=request.expression_scale,
                    input_yaw=request.input_yaw,
                    input_pitch=request.input_pitch,
                    input_roll=request.input_roll,
                    enhancer=request.enhancer,
                    background_enhancer=request.background_enhancer,
                    face3dvis=request.face3dvis,
                    still=request.still,
                    preprocess=request.preprocess,
                )
            )
        else:
            raise ValueError("Invalid Lipsync Model")

    def render_example(self, state: dict):
        output_video = state.get("output_video")
        if output_video:
            st.write("#### Output Video")
            st.video(output_video, autoplay=True, show_download_button=True)
        else:
            st.div()

    def render_output(self):
        self.render_example(st.session_state)

    def related_workflows(self) -> list:
        from recipes.DeforumSD import DeforumSDPage
        from recipes.LipsyncTTS import LipsyncTTSPage
        from recipes.asr_page import AsrPage
        from recipes.VideoBots import VideoBotsPage

        return [DeforumSDPage, LipsyncTTSPage, AsrPage, VideoBotsPage]

    def render_usage_guide(self):
        youtube_video("EJdtC0USujM")

    def preview_description(self, state: dict) -> str:
        return "Create high-quality, realistic Lipsync animations from any audio file. Input a sample face gif/video + audio and we will automatically generate a lipsync animation that matches your audio."

    def get_cost_note(self) -> str | None:
        multiplier = (
            3
            if st.session_state.get("lipsync_model") == LipsyncModel.SadTalker.name
            else 1
        )
        return f"{CREDITS_PER_MB * multiplier} credits per MB"

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
        multiplier = (
            3 if state.get("lipsync_model") == LipsyncModel.SadTalker.name else 1
        )
        return total_mb * CREDITS_PER_MB * multiplier
