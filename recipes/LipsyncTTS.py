import typing

from pydantic import BaseModel

import gooey_ui as st
from bots.models import Workflow
from daras_ai_v2.text_to_speech_settings_widgets import text_to_speech_provider_selector
from recipes.Lipsync import LipsyncPage
from recipes.TextToSpeech import TextToSpeechPage, TextToSpeechProviders
from daras_ai_v2.safety_checker import safety_checker
from daras_ai_v2.loom_video_widget import youtube_video

DEFAULT_LIPSYNC_TTS_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/13b4d352-9456-11ee-8edd-02420a0001c7/Lipsync%20TTS.jpg.png"


class LipsyncTTSPage(LipsyncPage, TextToSpeechPage):
    title = "Lipsync Video with Any Text"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/1acfa370-88d9-11ee-bf6c-02420a000166/Lipsync%20with%20audio%201.png.png"
    workflow = Workflow.LIPSYNC_TTS
    slug_versions = ["LipsyncTTS", "lipsync-maker"]

    sane_defaults = {
        "elevenlabs_voice_name": "Rachel",
        "elevenlabs_model": "eleven_multilingual_v2",
        "elevenlabs_stability": 0.5,
        "elevenlabs_similarity_boost": 0.75,
    }

    class RequestModel(BaseModel):
        input_face: str
        input_audio: str | None

        face_padding_top: int | None
        face_padding_bottom: int | None
        face_padding_left: int | None
        face_padding_right: int | None

        text_prompt: str

        tts_provider: str | None

        uberduck_voice_name: str | None
        uberduck_speaking_rate: float | None

        google_voice_name: str | None
        google_speaking_rate: float | None
        google_pitch: float | None

        bark_history_prompt: str | None

        elevenlabs_voice_name: str | None
        elevenlabs_api_key: str | None
        elevenlabs_voice_id: str | None
        elevenlabs_model: str | None
        elevenlabs_stability: float | None
        elevenlabs_similarity_boost: float | None
        elevenlabs_style: float | None
        elevenlabs_speaker_boost: bool | None

    class ResponseModel(BaseModel):
        output_video: str

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
        st.file_uploader(
            """
            #### Input Face
            Upload a video/image that contains faces to use
            *Recommended - mp4 / mov / png / jpg*
            """,
            key="input_face",
        )
        st.text_area(
            """
            #### Input Text
            This generates audio for your video
            """,
            key="text_prompt",
        )
        text_to_speech_provider_selector(self)

    def validate_form_v2(self):
        assert st.session_state.get(
            "text_prompt", ""
        ).strip(), "Text input cannot be empty"
        assert st.session_state.get("input_face"), "Please provide an Input Face"

    def preview_image(self, state: dict) -> str | None:
        return DEFAULT_LIPSYNC_TTS_META_IMG

    def preview_description(self, state: dict) -> str:
        return "Add your text prompt, pick a voice & upload a sample video to quickly create realistic lipsync videos. Discover the ease of text-to-video AI."

    def render_description(self):
        st.write(
            """
                This recipe takes any text and a video of a person (plus the voice defined in Settings) to create a lipsync'd video of that person speaking your text.

                How It Works:

                1. Takes any text + a video (with a face in it)
                2. Generates audio file in voice of your choice
                3. Merges the audio and video
                4. Renders a lipsynced video with your text
            """
        )

    def render_settings(self):
        LipsyncPage.render_settings(self)
        TextToSpeechPage.render_settings(self)

    def run(self, state: dict) -> typing.Iterator[str | None]:
        if not self.request.user.disable_safety_checker:
            safety_checker(text=state["text_prompt"])

        yield from TextToSpeechPage.run(self, state)
        # IMP: Copy output of TextToSpeechPage "audio_url" to Lipsync as "input_audio"
        state["input_audio"] = state["audio_url"]
        yield from LipsyncPage.run(self, state)

    def render_example(self, state: dict):
        output_video = state.get("output_video")
        if output_video:
            st.video(
                output_video,
                caption="#### Output Video",
                autoplay=True,
                show_download_button=True,
            )
        else:
            st.div()

    def render_output(self):
        self.render_example(st.session_state)

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
