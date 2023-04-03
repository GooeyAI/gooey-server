import typing

import streamlit as st
from pydantic import BaseModel

from daras_ai_v2.asr import (
    AsrModels,
    google_translate_language_selector,
    run_asr,
    run_google_translate,
)
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import (
    document_uploader,
    validate_upload_documents,
)
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.face_restoration import map_parallel
from daras_ai_v2.text_output_widget import text_outputs


class AsrPage(BasePage):
    title = "Speech Recognition & Translation"
    slug_versions = ["asr", "speech"]

    class RequestModel(BaseModel):
        documents: list[str] | None
        selected_model: typing.Literal[tuple(e.name for e in AsrModels)] | None
        google_translate_target: str | None

    class ResponseModel(BaseModel):
        asr_text: list[str] | None
        output_text: list[str]

    def preview_description(self, state: dict):
        return "Transcribe mp3, WhatsApp audio + wavs with OpenAI's Whisper or AI4Bharat / Bhashini ASR models. Optionally translate to any language too."

    def render_description(self):
        st.markdown(
            """
            This workflow let's you compare the latest and finest speech recognition models from [OpenAI](https://openai.com/research/whisper), [AI4Bharat](https://ai4bharat.org) and [Bhashini](https://bhashini.gov.in) and Google's USM coming soon.
            """
        )
        st.markdown(
            """
            Just upload an audio file (mp3, wav, ogg or aac file) setting its language and then choose a speech recognition engine. You can also translate the output to any language too (using Google's Translation APIs).
            """
        )

    def related_workflows(self) -> list:
        from recipes.VideoBots import VideoBotsPage
        from recipes.CompareLLM import CompareLLMPage
        from recipes.TextToSpeech import TextToSpeechPage

        from recipes.LipsyncTTS import LipsyncTTSPage

        return [
            VideoBotsPage,
            LipsyncTTSPage,
            TextToSpeechPage,
            CompareLLMPage,
        ]

    def render_form_v2(self):
        document_uploader("##### Audio Files", type=("wav", "ogg", "mp3", "aac"))
        enum_selector(AsrModels, label="###### ASR Model", key="selected_model")
        google_translate_language_selector()

    def validate_form_v2(self):
        validate_upload_documents()

    def render_output(self):
        text_outputs("**Transcription**", key="output_text", height=300)

    def render_example(self, state: dict):
        text_outputs("**Transcription**", key="output_text", height=200)

    def render_steps(self):
        if st.session_state.get("google_translate_target"):
            text_outputs("**Transcription**", key="asr_text", height=200)
            text_outputs("**Translation**", key="output_text", height=300)
        else:
            text_outputs("**Transcription**", key="output_text", height=200)

    def run(self, state: dict):
        # Parse Request
        request: AsrPage.RequestModel = self.RequestModel.parse_obj(state)

        # Run ASR
        selected_model = AsrModels[request.selected_model]
        yield f"Running {selected_model.value}..."
        state["output_text"] = map_parallel(
            lambda audio: run_asr(audio, selected_model=request.selected_model),
            request.documents,
        )

        # Run Translation
        if request.google_translate_target:
            state["asr_text"] = state["output_text"]  # Save ASR text for details view
            state["output_text"] = run_google_translate(
                state["output_text"],
                google_translate_target=request.google_translate_target,
            )
