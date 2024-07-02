import typing

import requests
from pydantic import BaseModel

import gooey_ui as st
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.lipsync_api import run_wav2lip, run_sadtalker, LipsyncSettings
from daras_ai_v2.lipsync_settings_widgets import lipsync_settings, LipsyncModel
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.pydantic_validation import FieldHttpUrl

CREDITS_PER_MINUTE = 36

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
        input_audio: FieldHttpUrl = None

    class ResponseModel(BaseModel):
        output_video: FieldHttpUrl
        seconds: float
        truncated: bool = False

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
        input_audio = st.session_state.get("input_audio")
        assert input_audio, "Please provide an Audio file"
        assert st.session_state.get("input_face"), "Please provide an Input Face"

    def render_settings(self):
        lipsync_settings(st.session_state.get("selected_model"))

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request = self.RequestModel.parse_obj(state)

        if self.is_current_user_paying() or self.is_current_user_admin():
            truncate_to_seconds = None
            state["truncated"] = False
        else:
            truncate_to_seconds = 10
            state["truncated"] = True

        model = LipsyncModel[request.selected_model]
        yield f"Running {model.value}..."
        match model:
            case LipsyncModel.Wav2Lip:
                state["output_video"], state["seconds"] = run_wav2lip(
                    face=request.input_face,
                    audio=request.input_audio,
                    pads=(
                        request.face_padding_top or 0,
                        request.face_padding_bottom or 0,
                        request.face_padding_left or 0,
                        request.face_padding_right or 0,
                    ),
                    truncate_to_seconds=truncate_to_seconds,
                )
            case LipsyncModel.SadTalker:
                state["output_video"], state["seconds"] = run_sadtalker(
                    request.sadtalker_settings,
                    face=request.input_face,
                    audio=request.input_audio,
                    truncate_to_seconds=truncate_to_seconds,
                )

    def render_example(self, state: dict):
        output_video = state.get("output_video")
        if output_video:
            st.write("#### Output Video")
            st.video(output_video, autoplay=True, show_download_button=True)
        else:
            st.div()
        if state.get("truncated"):
            st.error(
                "Audio durations greater than 10 seconds will be truncated for free users. Please upgrade to process longer audio files.",
                icon="⚠️",
                color="orange",
            )

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
            2
            if st.session_state.get("selected_model") == LipsyncModel.SadTalker.name
            else 1
        )
        return f"{CREDITS_PER_MINUTE * multiplier}/minute"

    def get_raw_price(self, state: dict) -> float:
        from math import ceil

        seconds = self.get_duration(state)
        seconds = ceil(seconds / 5) * 5  # round up to nearest 5 seconds
        multiplier = (
            2 if state.get("selected_model") == LipsyncModel.SadTalker.name else 1
        )
        return seconds * CREDITS_PER_MINUTE * multiplier / 60

    def get_duration(self, state: dict) -> float:
        return state.get("seconds", 0.0)
