import typing

from jinja2.lexer import whitespace_re
from pydantic import BaseModel, Field

import gooey_gui as gui
from bots.models import Workflow, SavedRun
from daras_ai_v2.asr import (
    language_filter_selector,
    asr_language_selector,
    AsrModels,
    AsrOutputFormat,
    AsrOutputJson,
    filter_models_by_language,
    forced_asr_languages,
    run_asr,
    run_translate,
    translation_language_selector,
    translation_model_selector,
    TranslationModels,
)
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import (
    bulk_documents_uploader,
    SUPPORTED_SPREADSHEET_TYPES,
)
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.field_render import field_title_desc
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.pydantic_validation import FieldHttpUrl
from daras_ai_v2.text_output_widget import text_outputs
from recipes.DocSearch import render_documents
from recipes.Translation import TranslationOptions

DEFAULT_ASR_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/1916825c-93fa-11ee-97be-02420a0001c8/Speech.jpg.png"

class AsrPage(BasePage):
    title = "Speech Recognition & Translation"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/5fb7e5f6-88d9-11ee-aa86-02420a000165/Speech.png.png"
    workflow = Workflow.ASR
    slug_versions = ["asr", "speech"]

    sane_defaults = dict(output_format=AsrOutputFormat.text.name)

    class RequestModelBase(BasePage.RequestModel):
        documents: list[FieldHttpUrl]
        selected_model: typing.Literal[tuple(e.name for e in AsrModels)] | None
        language: str | None

        translation_model: (
            typing.Literal[tuple(e.name for e in TranslationModels)] | None
        )

        output_format: typing.Literal[tuple(e.name for e in AsrOutputFormat)] | None

        google_translate_target: str | None = Field(
            deprecated=True,
            description="use `translation_model` & `translation_target` instead.",
        )

    class RequestModel(TranslationOptions, RequestModelBase):
        pass

    class ResponseModel(BaseModel):
        raw_output_text: list[str] | None
        output_text: list[str | AsrOutputJson]

    def current_sr_to_session_state(self) -> dict:
        state = super().current_sr_to_session_state()
        google_translate_target = state.pop("google_translate_target", None)
        translation_model = state.get("translation_model")
        if google_translate_target and not translation_model:
            state["translation_model"] = TranslationModels.google.name
            state["translation_target"] = google_translate_target
        return state

    @classmethod
    def get_example_preferred_fields(cls, state: dict) -> list[str]:
        return [
            "selected_model",
            "language",
            "translation_model",
            "translation_target",
        ]

    def preview_image(self, state: dict) -> str | None:
        return DEFAULT_ASR_META_IMG

    def preview_description(self, state: dict):
        return "Transcribe mp3, WhatsApp audio + wavs with OpenAI's Whisper or AI4Bharat / Bhashini ASR models. Optionally translate to any language too."

    def render_description(self):
        gui.markdown(
            """
            This workflow let's you compare the latest and finest speech recognition models from [OpenAI](https://openai.com/research/whisper), [AI4Bharat](https://ai4bharat.org) and [Bhashini](https://bhashini.gov.in) and Google's USM coming soon.
            """
        )
        gui.markdown(
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
        bulk_documents_uploader(
            "#### Audio Files",
            accept=("audio/*", "video/*", "application/octet-stream"),
        )
        gui.markdown("#### Speech Recognition")
        # drop down to filter models based on the selected language
        selected_filter_language = language_filter_selector()

        col1, col2 = gui.columns(2, responsive=False)
        supported_models = filter_models_by_language(
            selected_filter_language, AsrModels
        )
        with col1:
            selected_model = enum_selector(
                supported_models,
                label="###### Speech Recognition Model",
                key="selected_model",
                use_selectbox=True,
            )
        with col2:
            asr_language_selector(
                AsrModels[selected_model], filter_by_language=selected_filter_language
            )

        # Translation options
        if gui.checkbox(
            "#### Translate",
            value=bool(gui.session_state.get("translation_model")),
        ):
            with gui.div(style=dict(marginTop="-0.9rem")):
                gui.caption(
                    "Choose a model, source and target languages to translate recognized audio",
                )
            col1, col2 = gui.columns(2, responsive=True)
            with col1:
                translation_model = translation_model_selector(allow_none=False)
            with col2:
                if selected_filter_language:
                    gui.session_state["translation_target"] = selected_filter_language
                translation_language_selector(
                    model=translation_model,
                    label=f"###### {field_title_desc(self.RequestModel, 'translation_target')}",
                    key="translation_target",
                )
            if selected_model and translation_model:
                gui.write("---")
                translation_language_selector(
                    model=translation_model,
                    label=f"###### {field_title_desc(self.RequestModel, 'translation_source')}",
                    key="translation_source",
                    default_language="en",
                    filter_by_language=selected_filter_language,
                    allow_none=(
                        False
                        if selected_filter_language
                        else (
                            translation_model.supports_auto_detect
                            if translation_model
                            else True
                        )
                    ),
                )
            if translation_model and translation_model.supports_glossary:
                gui.file_uploader(
                    label=f"###### {field_title_desc(self.RequestModel, 'glossary_document')}",
                    key="glossary_document",
                    accept=SUPPORTED_SPREADSHEET_TYPES,
                )

                gui.caption(
                    "This is usually inferred from the spoken `language`, but in case that is set to Auto detect, you can specify one explicitly.",
                )
        else:
            gui.session_state["translation_model"] = None

    def render_settings(self):
        enum_selector(
            AsrOutputFormat, label="###### Output Format", key="output_format"
        )

    def validate_form_v2(self):
        assert gui.session_state.get(
            "documents"
        ), "Please provide at least 1 Audio File"

    def render_output(self):
        text_outputs("**Transcription**", key="output_text", height=300)

    def render_example(self, state: dict):
        render_documents(state)
        text_outputs("**Transcription**", value=state.get("output_text"))

    def render_steps(self):
        if gui.session_state.get("translation_model"):
            col1, col2 = gui.columns(2)
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
            max_workers=4,
        )

        # Save the raw ASR text for details view
        state["raw_output_text"] = asr_output
        # Run Translation
        if request.translation_model and request.translation_target:
            state["output_text"] = run_translate(
                asr_output,
                target_language=request.translation_target,
                source_language=forced_asr_languages.get(
                    selected_model, request.translation_source or request.language
                ),
                glossary_url=request.glossary_document,
                model=request.translation_model,
            )
        else:
            state["raw_output_text"] = None
            state["output_text"] = asr_output

    def get_cost_note(self) -> str | None:
        return "1 credit for 12.5 words ≈ 0.08 per word"

    def get_raw_price(self, state: dict):
        texts = state.get("output_text", [])
        total_words = sum(len(whitespace_re.split(str(out))) for out in texts)
        return 0.04 * total_words
