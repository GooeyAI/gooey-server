import typing

from pydantic import BaseModel, Field

import gooey_gui as gui
from bots.models import Workflow
from daras_ai_v2.asr import (
    TranslationModels,
    translation_model_selector,
    translation_language_selector,
    run_translate,
    language_filter_selector,
)
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import SUPPORTED_SPREADSHEET_TYPES
from daras_ai_v2.field_render import field_title_desc, field_title
from daras_ai_v2.language_filters import translation_languages_without_dialects
from daras_ai_v2.pydantic_validation import FieldHttpUrl
from daras_ai_v2.text_output_widget import text_outputs
from daras_ai_v2.workflow_url_input import del_button
from recipes.BulkRunner import list_view_editor


class TranslationOptions(BaseModel):
    translation_source: str | None = Field(
        None,
        title="Source Translation Language",
        description="This is usually inferred from the spoken language, but in case that is set to Auto detect, you can specify one explicitly.",
    )
    translation_target: str | None = Field(
        "en",
        title="Target Translation Language",
    )
    glossary_document: FieldHttpUrl | None = Field(
        None,
        title="Translation Glossary",
        description="""Provide a glossary to customize translation and improve accuracy of domain-specific terms.
If not specified or invalid, no glossary will be used. Read about the expected format [here](https://docs.google.com/document/d/1TwzAvFmFYekloRKql2PXNPIyqCbsHRL8ZtnWkzAYrh8/edit?usp=sharing).""",
    )


class TranslationPage(BasePage):
    title = "Compare AI Translations"
    workflow = Workflow.TRANSLATION
    slug_versions = ["translate", "translation", "compare-ai-translation"]

    class RequestModelBase(BasePage.RequestModel):
        texts: list[str] = Field([])

        selected_model: (
            (typing.Literal[tuple(e.name for e in TranslationModels)]) | None
        ) = Field(TranslationModels.google.name)

    class RequestModel(TranslationOptions, RequestModelBase):
        pass

    class ResponseModel(BaseModel):
        output_texts: list[str] = Field([])

    def run_v2(
        self,
        request: "TranslationPage.RequestModel",
        response: "TranslationPage.ResponseModel",
    ):
        yield f"Translating using {TranslationModels[request.selected_model].label}..."
        response.output_texts = run_translate(
            request.texts,
            request.translation_target,
            request.translation_source,
            request.glossary_document,
            request.selected_model,
        )

    @classmethod
    def get_example_preferred_fields(cls, state: dict) -> list[str]:
        return [
            "texts",
            "translation_model",
            "translation_target",
        ]

    def related_workflows(self) -> list:
        from recipes.asr_page import AsrPage
        from recipes.VideoBots import VideoBotsPage
        from recipes.TextToSpeech import TextToSpeechPage
        from recipes.LipsyncTTS import LipsyncTTSPage

        return [
            AsrPage,
            VideoBotsPage,
            TextToSpeechPage,
            LipsyncTTSPage,
        ]

    def render_form_v2(self):
        gui.write("###### Source Texts")
        list_view_editor(
            add_btn_label="Add Text",
            key="texts",
            render_inputs=render_text_input,
            flatten_dict_key="text",
        )

        selected_filter_language = language_filter_selector(
            options=translation_languages_without_dialects(),
        )

        col1, col2 = gui.columns(2)
        with col1:
            translation_model = translation_model_selector(
                key="selected_model",
                allow_none=False,
                language_filter=selected_filter_language,
            )

        col1, col2 = gui.columns(2)
        with col1:
            translation_language_selector(
                model=translation_model,
                label=f"###### {field_title(self.RequestModel, 'translation_source')}",
                key="translation_source",
                allow_none=not selected_filter_language,
                sort_by=selected_filter_language,
            )
        with col2:
            translation_language_selector(
                model=translation_model,
                label=f"###### {field_title_desc(self.RequestModel, 'translation_target')}",
                key="translation_target",
            )

    def render_settings(self):
        translation_model = TranslationModels.get(
            gui.session_state.get("selected_model")
        )
        if translation_model and translation_model.supports_glossary:
            gui.file_uploader(
                label=f"###### {field_title_desc(self.RequestModel, 'glossary_document')}",
                key="glossary_document",
                accept=SUPPORTED_SPREADSHEET_TYPES,
            )
        else:
            gui.session_state["glossary_document"] = None

    def validate_form_v2(self):
        non_empty_text_inputs = [
            text for text in gui.session_state.get("texts") if text
        ]
        assert non_empty_text_inputs, "Please provide at least 1 non-empty text input"

    def render_output(self):
        text_outputs("**Translations**", key="output_texts", height=300)

    def render_run_preview_output(self, state: dict):
        text_outputs("**Translations**", value=state.get("output_texts", []))

    def render_steps(self):
        gui.markdown(
            """
            1. Apply Transliteration as necessary.
            """
        )
        gui.markdown(
            """
            2. Detect the source language if not provided.
            """
        )
        gui.markdown(
            """
            3. Translate with the selected API (for Auto, we look up the optimal API based on the detected language and script).
            """
        )
        gui.markdown(
            """
            4. Apply romanization if requested and applicable.
            """
        )

    def get_cost_note(self) -> str | None:
        return "1 + 0.006 per unicode character ≈ 1 + 3 per word"

    def get_raw_price(self, state: dict):
        texts = state.get("texts", [])
        characters = sum([len(text) for text in texts])
        return 1 + 0.006 * characters


def render_text_input(key: str, del_key: str, d: dict):
    col1, col2 = gui.columns([8, 1], responsive=False)
    with col1:
        with gui.div(className="pt-1"):
            d["text"] = gui.text_area(
                "",
                label_visibility="collapsed",
                key=key + ":text",
                value=d.get("text"),
            )
    with col2:
        del_button(del_key)
