import typing

from jinja2.lexer import whitespace_re
from pydantic import BaseModel

import gooey_ui as st
from bots.models import Workflow
from daras_ai_v2.asr import (
    AsrModels,
    google_translate_language_selector,
    run_asr,
    run_google_translate,
    AsrOutputFormat,
    AsrOutputJson,
    forced_asr_languages,
    asr_language_selector,
)
from daras_ai_v2.glossary import glossary_input
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import (
    document_uploader,
)
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.text_output_widget import text_outputs
from recipes.DocSearch import render_documents

DEFAULT_ASR_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/1916825c-93fa-11ee-97be-02420a0001c8/Speech.jpg.png"


class AsrPage(BasePage):
    title = "Speech Recognition & Translation"
    image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/5fb7e5f6-88d9-11ee-aa86-02420a000165/Speech.png.png"
    workflow = Workflow.ASR
    slug_versions = ["asr", "speech"]

    sane_defaults = dict(output_format=AsrOutputFormat.text.name)

    class RequestModel(BaseModel):
        documents: list[str]
        selected_model: typing.Literal[tuple(e.name for e in AsrModels)] | None
        language: str | None
        google_translate_target: str | None
        glossary_document: str | None
        output_format: typing.Literal[tuple(e.name for e in AsrOutputFormat)] | None

    class ResponseModel(BaseModel):
        raw_output_text: list[str] | None
        output_text: list[str | AsrOutputJson]

    def preview_image(self, state: dict) -> str | None:
        return DEFAULT_ASR_META_IMG

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
        document_uploader(
            "##### Audio Files",
            accept=("audio/*", "video/*", "application/octet-stream"),
        )
        col1, col2 = st.columns(2, responsive=False)
        with col1:
            selected_model = enum_selector(
                AsrModels,
                label="##### ASR Model",
                key="selected_model",
                use_selectbox=True,
            )
        with col2:
            asr_language_selector(AsrModels[selected_model])

    def render_settings(self):
        google_translate_language_selector()
        glossary_input()
        st.write("---")
        enum_selector(
            AsrOutputFormat, label="###### Output Format", key="output_format"
        )

    def validate_form_v2(self):
        assert st.session_state.get("documents"), "Please provide at least 1 Audio File"

    def render_output(self):
        text_outputs("**Transcription**", key="output_text", height=300)

    def render_example(self, state: dict):
        render_documents(state)
        text_outputs("**Transcription**", value=state.get("output_text"))

    def render_steps(self):
        if st.session_state.get("google_translate_target"):
            col1, col2 = st.columns(2)
            with col1:
                text_outputs("**Transcription**", key="raw_output_text")
            with col2:
                text_outputs("**Translation**", key="output_text")
        else:
            text_outputs("**Transcription**", key="output_text")

    def run(self, state: dict):
        # Parse Request
        request: AsrPage.RequestModel = self.RequestModel.parse_obj(state)

        # Run ASR
        selected_model = AsrModels[request.selected_model]
        yield f"Running {selected_model.value}..."
        asr_output = map_parallel(
            lambda audio: run_asr(
                audio_url=audio,
                selected_model=request.selected_model,
                language=request.language,
                output_format=request.output_format,
            ),
            request.documents,
        )

        # Run Translation
        if request.google_translate_target:
            # Save the raw ASR text for details view
            state["raw_output_text"] = asr_output
            # Run Translation
            state["output_text"] = run_google_translate(
                asr_output,
                target_language=request.google_translate_target,
                source_language=forced_asr_languages.get(
                    selected_model, request.language
                ),
                glossary_url=request.glossary_document,
            )
        else:
            # Save the raw ASR text for details view
            state["output_text"] = asr_output

    def get_cost_note(self) -> str | None:
        return "1 credit for 12.5 words ≈ 0.08 per word"

    def get_raw_price(self, state: dict):
        texts = state.get("output_text", [])
        total_words = sum(len(whitespace_re.split(str(out))) for out in texts)
        return 0.04 * total_words
