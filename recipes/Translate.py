import gooey_ui as st
from typing import Iterator
from pydantic import BaseModel

from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import (
    document_uploader,
)
from daras_ai_v2.text_output_widget import text_outputs
from recipes.DocSearch import render_documents
from daras_ai_v2.translate import (
    Translate,
    TranslateUI,
    TRANSLATE_API_TYPE,
    LANGUAGE_CODE_TYPE,
    DEFAULT_GLOSSARY_URL,
)
from daras_ai_v2.vector_search import download_text_doc


class TranslationPage(BasePage):
    title = "Compare AI Translation Tools"
    slug_versions = ["languages", "transliteration", "translate"]

    sane_defaults = dict(
        translate_api=Translate.APIs.GoogleTranslate.name,
        target_language="en",
        enable_transliteration=True,
        glossary_url=DEFAULT_GLOSSARY_URL,
    )

    class RequestModel(BaseModel):
        texts: list[str] | None
        documents: list[str] | None
        translate_api: TRANSLATE_API_TYPE | None
        target_language: LANGUAGE_CODE_TYPE | None
        source_language: LANGUAGE_CODE_TYPE | None

        enable_transliteration: bool | None
        glossary_url: str | None

    class ResponseModel(BaseModel):
        output_texts: list[str]
        output_docs: list[list[str]]

    def preview_description(self, state: dict):
        return "Translate your text to over 200+ languages using the best AI private and public translation and transliteration tools available from Google, Meta, [WikiMedia](https://diff.wikimedia.org/2023/06/13/mint-supporting-underserved-languages-with-open-machine-translation/) & more. Includes support from [Google Translate](https://cloud.google.com/translate), NLLB-200 (No Language Left Behind project), [OPUS](https://opus.nlpl.eu/), [IndicTrans2](https://ai4bharat.iitm.ac.in/indic-trans2) and [Softcatala](https://github.com/Softcatala/nmt-softcatala)."

    def run(self, state: dict) -> Iterator[str | None]:
        # Parse Request
        request: TranslationPage.RequestModel = self.RequestModel.parse_obj(state)
        yield "Translating Text Inputs..."
        state["output_texts"] = Translate.run(
            request.texts,
            request.target_language,
            request.translate_api,
            request.source_language,
            request.enable_transliteration,
            glossary_url=request.glossary_url,
        )
        yield "Translating Documents..."
        state["output_docs"] = [
            Translate.run(
                download_text_doc(doc),
                request.target_language,
                request.translate_api,
                request.source_language,
                request.enable_transliteration,
                glossary_url=request.glossary_url,
            )
            for doc in request.documents
        ]

    def render_description(self):
        st.markdown(
            """
            Translate your text to over 200+ languages using the best AI private and public translation and transliteration tools available from Google, Meta, [WikiMedia](https://diff.wikimedia.org/2023/06/13/mint-supporting-underserved-languages-with-open-machine-translation/) & more. Includes support from [Google Translate](https://cloud.google.com/translate), NLLB-200 (No Language Left Behind project), [OPUS](https://opus.nlpl.eu/), [IndicTrans2](https://ai4bharat.iitm.ac.in/indic-trans2) and [Softcatala](https://github.com/Softcatala/nmt-softcatala).
            """
        )

    def related_workflows(self) -> list:
        from recipes.asr import AsrPage
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
        num_inputs = st.number_input(
            """
            ##### Text Inputs
            Select how many texts you want to translate:
            """,
            0,
            100,
            1,
            1,
        )
        texts = st.session_state.get("texts", [])
        st.caption("Enter text (in any language) that you'd like to translate:")
        st.session_state["texts"] = [
            st.text_area(
                f"""
                Text Input {i + 1}
                """,
                value=text,
            )
            for i, text in enumerate(
                (texts + [""] * (num_inputs - len(texts)))[:num_inputs]
            )
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
        st.checkbox(
            """
            Enable Transliteration
            """,
            key="enable_transliteration",
        )
        st.caption(
            "Detects romanized input text and transliterates it to non-Latin characters where neccessary (and supported) before passing it to the translation models, e.g. this will turn Namaste into नमस्ते which makes it easier for the translation models to understand.\nSee [Romanization/Transliteration](https://guides.library.harvard.edu/mideast/romanization#:~:text=Romanization%%20refers%20to%20the%20process,converting%%20one%%20script%%20into%%20another.)"
        )
        TranslateUI.translate_glossary_input()

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
        text_outputs("**Translation**", key="output_texts")
        if state.get("documents", False):
            text_outputs("*Documents*", key="output_docs")

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

    def additional_notes(self) -> str | None:
        return """
            *Cost ≈ 3 credit for 100 words (or 500 unicode characters for non English languages) ≈ 0.03 credits per word (0.006 credits per unicode character)*
        """

    def get_raw_price(self, state: dict):
        texts = state.get("texts", [])
        characters = sum([len(text) for text in texts])
        return 0.006 * characters


def translate_settings(
    require_api=False,
    key_apiselect="translate_api",
    require_target=False,
    key_target="target_language",
    require_source=False,
    key_source="source_language",
):
    translator = TranslateUI.translate_api_selector(
        key=key_apiselect, allow_none=not require_api
    )
    translator.language_selector(
        label="""
        ###### Input Language
        Automatically detect language if not specified. If this is the same as the target language, transliteration will be applied if enabled, otherwise no translation will take place.
        """,
        key=key_source,
        allow_none=not require_source,
    )
    translator.language_selector(key=key_target, allow_none=not require_target)
