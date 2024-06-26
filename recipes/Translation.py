import typing

from pydantic import BaseModel, Field, HttpUrl

import gooey_ui as st
from bots.models import Workflow
from daras_ai_v2.asr import (
    TranslationModels,
    translation_model_selector,
    translation_language_selector,
    run_translate,
)
from daras_ai_v2.base import BasePage
from daras_ai_v2.field_render import field_title_desc
from daras_ai_v2.glossary import glossary_input
from daras_ai_v2.text_output_widget import text_outputs


class TranslationPage(BasePage):
    title = "Compare AI Translations"
    workflow = Workflow.TRANSLATION
    slug_versions = ["translate", "translation", "compare-ai-translation"]

    class RequestModel(BaseModel):
        texts: list[str] = Field([])

        translation_model: (
            typing.Literal[tuple(e.name for e in TranslationModels)]
        ) | None = Field(TranslationModels.google.name)

        translation_source: str | None = Field(
            title="Source Translation Language",
        )
        translation_target: str = Field(
            "en",
            title="Target Translation Language",
        )

        glossary_document: HttpUrl | None = Field(
            title="Glossary Document",
            description="A document containing translations for specific terms (only supported with Google Translate).",
        )

    class ResponseModel(BaseModel):
        output_texts: list[str]

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
        texts = st.session_state.get("texts", [])
        num_inputs = st.session_state.get("__num_inputs", 1)
        st.session_state["texts"] = [
            st.text_area(
                f"""
                Text Input {i + 1 if num_inputs > 1 else ""}
                """,
                value=text,
            )
            for i, text in enumerate(
                (texts + [""] * (num_inputs - len(texts)))[:num_inputs]
            )
        ]
        if st.button("Add Text Input"):
            st.session_state["__num_inputs"] = num_inputs + 1
            st.experimental_rerun()

        st.write("---")
        translation_model = translation_model_selector(allow_none=False)
        translation_language_selector(
            model=translation_model,
            label=f"###### {field_title_desc(self.RequestModel, 'translation_source')}",
            key="translation_source",
            allow_none=True,
        )
        translation_language_selector(
            model=translation_model,
            label=f"###### {field_title_desc(self.RequestModel, 'translation_target')}",
            key="translation_target",
        )

    def render_settings(self):
        translation_model = TranslationModels[st.session_state.get("translation_model")]
        if translation_model and translation_model.supports_glossary():
            glossary_input(
                label=f"###### {field_title_desc(self.RequestModel, 'glossary_document')}",
                key="glossary_document",
            )
            if not st.session_state["glossary_document"].strip():
                st.session_state["glossary_document"] = None
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

    def run(self, state: dict):
        request: TranslationPage.RequestModel = self.RequestModel.parse_obj(state)

        yield f"Translating using {TranslationModels[request.translation_model].value}..."
        state["output_texts"] = run_translate(
            request.texts,
            request.translation_target,
            request.translation_source,
            request.glossary_document,
            request.translation_model,
        )

    def get_cost_note(self) -> str | None:
        return "1 + 0.006 per unicode character ≈ 1 + 3 per word"

    def get_raw_price(self, state: dict):
        texts = state.get("texts", [])
        characters = sum([len(text) for text in texts])
        return 1 + 0.006 * characters
