import typing

from pydantic import BaseModel

import gooey_gui as gui
from bots.models import Workflow
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.lipsync_api import LipsyncSettings, LipsyncModel
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.pydantic_validation import HttpUrlStr
from daras_ai_v2.safety_checker import safety_checker
from daras_ai_v2.text_to_speech_settings_widgets import (
    text_to_speech_provider_selector,
)
from recipes.Lipsync import LipsyncPage
from recipes.TextToSpeech import TextToSpeechPage, TextToSpeechProviders


class LipsyncTTSPage(LipsyncPage, TextToSpeechPage):
    title = "Lipsync Video with Any Text"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/1acfa370-88d9-11ee-bf6c-02420a000166/Lipsync%20with%20audio%201.png.png"
    workflow = Workflow.LIPSYNC_TTS
    slug_versions = ["LipsyncTTS", "lipsync-maker"]

    sane_defaults = {
        "elevenlabs_model": "eleven_multilingual_v2",
        "elevenlabs_stability": 0.5,
        "elevenlabs_similarity_boost": 0.75,
    }

    class RequestModel(LipsyncSettings, TextToSpeechPage.RequestModel):
        selected_model: typing.Literal[tuple(e.name for e in LipsyncModel)] = (
            LipsyncModel.Wav2Lip.name
        )

    class ResponseModel(BaseModel):
        audio_url: str | None = None

        output_video: HttpUrlStr
        duration_sec: float | None = None

    def related_workflows(self) -> list:
        from recipes.VideoBots import VideoBotsPage
        from recipes.DeforumSD import DeforumSDPage

        return [
            VideoBotsPage,
            TextToSpeechPage,
            DeforumSDPage,
            LipsyncPage,
        ]

    def render_form_v2(self):
        gui.file_uploader(
            """
            #### Input Face
            Upload a video/image with one human face.
            *Recommended - mp4 / mov / png / jpg*
            """,
            key="input_face",
        )
        gui.text_area(
            """
            #### Input Text
            This generates audio for your video
            """,
            key="text_prompt",
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

        text_to_speech_provider_selector(self)

    def validate_form_v2(self):
        assert gui.session_state.get("text_prompt", "").strip(), (
            "Text input cannot be empty"
        )
        assert gui.session_state.get("input_face"), "Please provide an Input Face"

    def render_description(self):
        gui.write(
            """
                This recipe takes any text and a video of a person (plus the voice defined in Settings) to create a lipsync'd video of that person speaking your text.

                How It Works:

                1. Takes any text + a video (with a face in it)
                2. Generates audio file in voice of your choice
                3. Merges the audio and video
                4. Renders a lipsynced video with your text
            """
        )

    def render_steps(self):
        audio_url = gui.session_state.get("audio_url")
        gui.audio(audio_url, caption="Output Audio", show_download_button=True)

    def render_settings(self):
        LipsyncPage.render_settings(self)
        TextToSpeechPage.render_settings(self)

    def run(self, state: dict) -> typing.Iterator[str | None]:
        if not self.request.user.disable_safety_checker:
            safety_checker(text=state["text_prompt"])

        yield from TextToSpeechPage(request=self.request).run(state)
        # IMP: Copy output of TextToSpeechPage "audio_url" to Lipsync as "input_audio"
        state["input_audio"] = state["audio_url"]
        yield from LipsyncPage(request=self.request).run(state)

    def render_run_preview_output(self, state: dict):
        output_video = state.get("output_video")
        if output_video:
            gui.video(
                output_video,
                caption="#### Output Video",
                autoplay=True,
                show_download_button=True,
            )
        else:
            gui.div()

    def render_output(self):
        self.render_run_preview_output(gui.session_state)

    def get_raw_price(self, state: dict):
        # _get_tts_provider comes from TextToSpeechPage
        if self._get_tts_provider(state) == TextToSpeechProviders.ELEVEN_LABS:
            return LipsyncPage.get_raw_price(
                self, state
            ) + TextToSpeechPage.get_raw_price(self, state)
        else:
            return LipsyncPage.get_raw_price(self, state)

    def get_cost_note(self):
        return "Lipsync cost + TTS cost"

    def additional_notes(self):
        cost_notes = {
            "Lipsync": LipsyncPage.get_cost_note(self),
            "TTS": TextToSpeechPage.get_cost_note(self),
        }
        notes = "\n".join(
            [f"- *{k} cost: {v.strip()}*" if v else "" for k, v in cost_notes.items()]
        )

        notes += LipsyncPage.additional_notes(self) or ""
        notes += TextToSpeechPage.additional_notes(self) or ""

        return notes

    def render_usage_guide(self):
        youtube_video("RRmwQR-IytI")
