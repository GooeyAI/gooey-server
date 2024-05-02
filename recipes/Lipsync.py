import typing

import requests
from pydantic import BaseModel, HttpUrl

import gooey_ui as st
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.lipsync_api import run_wav2lip, run_sadtalker, LipsyncSettings
from daras_ai_v2.lipsync_settings_widgets import lipsync_settings, LipsyncModel
from daras_ai_v2.loom_video_widget import youtube_video

CREDITS_PER_MB = 2

DEFAULT_LIPSYNC_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/7fc4d302-9402-11ee-98dc-02420a0001ca/Lip%20Sync.jpg.png"


class LipsyncPage(BasePage):
    title = "Lip Syncing"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/f33e6332-88d8-11ee-89f9-02420a000169/Lipsync%20TTS.png.png"
    workflow = Workflow.LIPSYNC
    slug_versions = ["Lipsync"]

    class RequestModel(LipsyncSettings, BaseModel):
        selected_model: typing.Literal[tuple(e.name for e in LipsyncModel)] = (
            LipsyncModel.Wav2Lip.name
        )
        input_audio: HttpUrl = None

    class ResponseModel(BaseModel):
        output_video: HttpUrl

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

        enum_selector(
            LipsyncModel,
            label="###### Lipsync Model",
            key="selected_model",
            use_selectbox=True,
        )

    def validate_form_v2(self):
        assert st.session_state.get("input_audio"), "Please provide an Audio file"
        assert st.session_state.get("input_face"), "Please provide an Input Face"

    def render_settings(self):
        lipsync_settings(st.session_state.get("selected_model"))

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request = self.RequestModel.parse_obj(state)

        model = LipsyncModel[request.selected_model]
        yield f"Running {model.value}..."
        match model:
            case LipsyncModel.Wav2Lip:
                state["output_video"] = run_wav2lip(
                    face=request.input_face,
                    audio=request.input_audio,
                    pads=(
                        request.face_padding_top or 0,
                        request.face_padding_bottom or 0,
                        request.face_padding_left or 0,
                        request.face_padding_right or 0,
                    ),
                )
            case LipsyncModel.SadTalker:
                state["output_video"] = run_sadtalker(
                    request.sadtalker_settings,
                    face=request.input_face,
                    audio=request.input_audio,
                )

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
