import typing

from pydantic import BaseModel, Field

import gooey_ui as st
from bots.models import Workflow
from daras_ai_v2.asr import (
    TranslationModels,
    translation_model_selector,
    translation_language_selector,
    run_translate,
)
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import SUPPORTED_SPREADSHEET_TYPES
from daras_ai_v2.field_render import field_title_desc
from daras_ai_v2.pydantic_validation import FieldHttpUrl
from daras_ai_v2.text_output_widget import text_outputs
from daras_ai_v2.workflow_url_input import del_button
from recipes.BulkRunner import list_view_editor


class TranslationOptions(BaseModel):
    translation_source: str | None = Field(
        title="Source Translation Language",
    )
    translation_target: str | None = Field(
        "en",
        title="Target Translation Language",
    )
    glossary_document: FieldHttpUrl | None = Field(
        title="Translation Glossary",
        description="""Provide a glossary to customize translation and improve accuracy of domain-specific terms.
If not specified or invalid, no glossary will be used. Read about the expected format [here](https://docs.google.com/document/d/1TwzAvFmFYekloRKql2PXNPIyqCbsHRL8ZtnWkzAYrh8/edit?usp=sharing).""",
    )


class TranslationPage(BasePage):
    title = "Compare AI Translations"
    workflow = Workflow.TRANSLATION
    slug_versions = ["translate", "translation", "compare-ai-translation"]

    class BaseRequestModel(BaseModel):
        texts: list[str] = Field([])

        selected_model: (
            typing.Literal[tuple(e.name for e in TranslationModels)]
        ) | None = Field(TranslationModels.google.name)

    class RequestModel(TranslationOptions, BaseRequestModel):
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
        st.write("###### Source Texts")
        list_view_editor(
            add_btn_label="➕ Add Text",
            key="texts",
            render_inputs=render_text_input,
            flatten_dict_key="text",
        )

        translation_model = translation_model_selector(
            key="selected_model",
            allow_none=False,
        )
        col1, col2 = st.columns(2)
        with col1:
            translation_language_selector(
                model=translation_model,
                label=f"###### {field_title_desc(self.RequestModel, 'translation_source')}",
                key="translation_source",
                allow_none=translation_model.supports_auto_detect,
            )
        with col2:
            translation_language_selector(
                model=translation_model,
                label=f"###### {field_title_desc(self.RequestModel, 'translation_target')}",
                key="translation_target",
            )

    def render_settings(self):
        try:
            translation_model = TranslationModels[
                st.session_state.get("selected_model")
            ]
        except KeyError:
            translation_model = None
        if translation_model and translation_model.supports_glossary:
            st.file_uploader(
                label=f"###### {field_title_desc(self.RequestModel, 'glossary_document')}",
                key="glossary_document",
                accept=SUPPORTED_SPREADSHEET_TYPES,
            )
        else:
            st.session_state["glossary_document"] = None

    def validate_form_v2(self):
        non_empty_text_inputs = [text for text in st.session_state.get("texts") if text]
        assert non_empty_text_inputs, "Please provide at least 1 non-empty text input"

    def render_output(self):
        text_outputs("**Translations**", key="output_texts", height=300)

    def render_example(self, state: dict):
        text_outputs("**Translations**", value=state.get("output_texts", []))

    def render_steps(self):
        st.markdown(
            """
            1. Apply Transliteration as necessary.
            """
        )
        st.markdown(
            """
            2. Detect the source language if not provided.
            """
        )
        st.markdown(
            """
            3. Translate with the selected API (for Auto, we look up the optimal API based on the detected language and script).
            """
        )
        st.markdown(
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
    col1, col2 = st.columns([8, 1], responsive=False)
    with col1:
        with st.div(className="pt-1"):
            d["text"] = st.text_area(
                "",
                label_visibility="collapsed",
                key=key + ":text",
                value=d.get("text"),
            )
    with col2:
        del_button(del_key)
