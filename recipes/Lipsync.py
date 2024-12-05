import typing
from math import ceil

import gooey_gui as gui
from pydantic import BaseModel

from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.lipsync_api import run_wav2lip, run_sadtalker, LipsyncSettings
from daras_ai_v2.lipsync_settings_widgets import lipsync_settings, LipsyncModel
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.pydantic_validation import FieldHttpUrl

DEFAULT_LIPSYNC_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/7fc4d302-9402-11ee-98dc-02420a0001ca/Lip%20Sync.jpg.png"


CREDITS_PER_MINUTE = 36


def price_for_model(selected_model: str | None) -> float:
    if selected_model == LipsyncModel.SadTalker.name:
        multiplier = 2
    else:
        multiplier = 1
    return CREDITS_PER_MINUTE * multiplier


class LipsyncPage(BasePage):
    title = "Lip Syncing"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/f33e6332-88d8-11ee-89f9-02420a000169/Lipsync%20TTS.png.png"
    workflow = Workflow.LIPSYNC
    slug_versions = ["Lipsync"]

    class RequestModel(LipsyncSettings, BasePage.RequestModel):
        selected_model: typing.Literal[tuple(e.name for e in LipsyncModel)] = (
            LipsyncModel.Wav2Lip.name
        )
        input_audio: FieldHttpUrl = None

    class ResponseModel(BaseModel):
        output_video: FieldHttpUrl
        duration_sec: float | None

    def preview_image(self, state: dict) -> str | None:
        return DEFAULT_LIPSYNC_META_IMG

    def render_form_v2(self):
        gui.file_uploader(
            """
            #### Input Face
            Upload a video/image with one human face.
            *Recommended - mp4 / mov / png / jpg* 
            """,
            key="input_face",
        )

        gui.file_uploader(
            """
            #### Input Audio
            Add a video/audio file as the lipsync audio source.
            *Recommended - mp4 / mov / wav / mp3*
            """,
            key="input_audio",
        )
        if not (self.is_current_user_paying() or self.is_current_user_admin()):
            gui.error(
                "Output videos will be truncated to 250 frames for free users. Please [upgrade](/account) to generate long videos.",
                icon="⚠️",
                color="#ffe8b2",
            )

        enum_selector(
            LipsyncModel,
            label="###### Lipsync Model",
            key="selected_model",
            use_selectbox=True,
        )

    def validate_form_v2(self):
        assert gui.session_state.get("input_audio"), "Please provide an Audio file"
        assert gui.session_state.get("input_face"), "Please provide an Input Face"

    def render_settings(self):
        lipsync_settings(gui.session_state.get("selected_model"))

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request = self.RequestModel.parse_obj(state)

        if self.is_current_user_paying() or self.is_current_user_admin():
            max_frames = None
        else:
            max_frames = 250

        model = LipsyncModel[request.selected_model]
        yield f"Running {model.value}..."
        match model:
            case LipsyncModel.Wav2Lip:
                state["output_video"], state["duration_sec"] = run_wav2lip(
                    face=request.input_face,
                    audio=request.input_audio,
                    pads=(
                        request.face_padding_top or 0,
                        request.face_padding_bottom or 0,
                        request.face_padding_left or 0,
                        request.face_padding_right or 0,
                    ),
                    max_frames=max_frames,
                )
            case LipsyncModel.SadTalker:
                state["output_video"], state["duration_sec"] = run_sadtalker(
                    request.sadtalker_settings,
                    face=request.input_face,
                    audio=request.input_audio,
                    max_frames=max_frames,
                )

    def render_example(self, state: dict):
        output_video = state.get("output_video")
        if output_video:
            gui.write("#### Output Video")
            gui.video(output_video, autoplay=True, show_download_button=True)
        else:
            gui.div()

    def render_output(self):
        self.render_example(gui.session_state)

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
        selected_model = gui.session_state.get("selected_model")
        return f"{price_for_model(selected_model)}/minute"

    def get_raw_price(self, state: dict) -> float:
        try:
            duration_sec = state["duration_sec"]
        except KeyError:
            return 1
        duration_sec = ceil(duration_sec / 5) * 5  # round up to nearest 5 seconds

        price = price_for_model(state.get("selected_model"))

        return duration_sec / 60 * price
