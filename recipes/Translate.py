import gooey_ui as st
from typing import Literal
from pydantic import BaseModel
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import (
    document_uploader,
)
from daras_ai_v2.text_output_widget import text_outputs
from recipes.DocSearch import render_documents
from daras_ai_v2.translate import (
    TranslateAPIs,
    translate_languages,
    translate_settings,
    translate_advanced_settings,
    run_translate,
)
from daras_ai_v2.vector_search import download_text_doc


class TranslationPage(BasePage):
    title = "Translation"
    slug_versions = ["languages", "transliteration", "translate"]

    sane_defaults = dict(
        translate_api=TranslateAPIs.Auto.name,
        translate_target="en",
        enable_transliteration=True,
        romanize_translation=False,
    )

    class RequestModel(BaseModel):
        texts: list[str] | None
        documents: list[str] | None
        translate_api: Literal[tuple(e.name for e in TranslateAPIs)] | None
        translate_target: Literal[
            tuple(code for code, language in translate_languages().items())
        ] | None
        translate_source: Literal[
            tuple(code for code, language in translate_languages().items())
        ] | None

        enable_transliteration: bool | None
        romanize_translation: bool | None

    class ResponseModel(BaseModel):
        output_texts: list[str]
        output_docs: list[list[str]]

    def preview_description(self, state: dict):
        return "Translate to any of 200+ languages using different APIs and models."

    def render_description(self):
        st.markdown(
            """
            This workflow let's you compare the latest and finest translation models and APIs.
            """
        )
        st.markdown(
            """
            Just upload one or more text files and/or paste in some text.
            """
        )
        st.markdown(
            """
            Try out important features like Transliteration and Romanization.
            """
        )

    def related_workflows(self) -> list:
        from recipes.asr import AsrPage
        from recipes.Text2Audio import Text2AudioPage
        from recipes.TextToSpeech import TextToSpeechPage
        from recipes.LipsyncTTS import LipsyncTTSPage

        return [
            AsrPage,
            TextToSpeechPage,
            Text2AudioPage,
            LipsyncTTSPage,
        ]

    def render_form_v2(self):
        st.session_state["texts"] = [
            st.text_area(
                f"""
                Text Input {i + 1}
                """
            )
            for i in range(st.number_input("""##### Text Inputs""", 0, 100, 1, 1))
        ]

        if st.checkbox(
            "Upload Text Files", value=bool(st.session_state.get("documents"))
        ):
            document_uploader(
                "",
                accept=(
                    ".pdf",
                    ".txt",
                    ".docx",
                    ".md",
                    ".html",
                    ".rtf",
                    ".epub",
                    ".odt",
                    ".csv",
                    ".xlsx",
                    ".tsv",
                    ".ods",
                ),
            )
        else:
            st.session_state["documents"] = []

        st.write("---")
        translate_settings(require_api=True, require_target=True)

    def render_settings(self):
        translate_advanced_settings()

    def validate_form_v2(self):
        non_empty_text_inputs = [text for text in st.session_state.get("texts") if text]
        assert non_empty_text_inputs or st.session_state.get(
            "documents"
        ), "Please provide at least 1 non-empty Text File or Input"

    def render_output(self):
        self._render_output(st.session_state)

    def render_example(self, state: dict):
        text_outputs("Input Texts", value=state.get("texts"))
        render_documents(state)
        self._render_output(state)

    def _render_output(self, state):
        print(state.get("texts"))
        print(state.get("output_texts", "not yet"))
        text_outputs("**Translations**", key="output_texts")
        text_outputs("", value=state.get("output_docs"))

    def render_steps(self):
        st.markdown(
            """
            1. Apply Transliteration necessary.
            """
        )
        st.markdown(
            """
            2. Translate with the selected API (for Auto, we look up the optimal API in a table).
            """
        )
        st.markdown(
            """
            3. Apply romanization if requested and applicable.
            """
        )

    def run(self, state: dict):
        # Parse Request
        request: TranslationPage.RequestModel = self.RequestModel.parse_obj(state)
        yield f"Running...123"
        state["output_texts"] = ["why?!!"]
        # state["output_texts"] = run_translate(
        #     request.texts, request.translate_target, request.translate_api
        # )

    def additional_notes(self) -> str | None:
        return """
            *Cost ≈ 1 credit for 100 words (or 500 unicode characters for non English languages) ≈ 0.01 credits per word (0.002 credits per unicode character)*
        """

    def get_raw_price(self, state: dict):
        if state.get("translation_api") == TranslateAPIs.MinT:
            return 1
        texts = state.get("texts", [])
        characters = sum([len(text) for text in texts])
        return 0.002 * characters
