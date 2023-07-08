import gooey_ui as st
from pydantic import BaseModel
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import (
    document_uploader,
)
from daras_ai_v2.text_output_widget import text_outputs
from recipes.DocSearch import render_documents
from daras_ai_v2.translate import (
    TranslateAPIs,
    translate_api_selector,
    translate_language_selector,
    run_translate,
)


class TranslationPage(BasePage):
    title = "Translation"
    slug_versions = ["languages", "transliteration", "translate"]

    sane_defaults = dict(translate_api=TranslateAPIs.MinT.name)

    class RequestModel(BaseModel):
        texts: list[str]
        documents: list[str]
        translate_target: str | None
        translate_api: TranslateAPIs | None

        enable_transliteration: bool

    class ResponseModel(BaseModel):
        output_texts: list[str]
        output_documents: list[str]

    def preview_description(self, state: dict):
        return "Translate to any (supported) language."

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

        document_uploader(
            "##### Text Files",
            accept="text/*",
        )
        st.write("---")
        translate_api_selector()
        translate_language_selector()

    def render_settings(self):
        st.checkbox(
            """
            Enable Transliteration
            """,
            False,
        )

    def validate_form_v2(self):
        assert st.session_state.get("documents"), "Please provide at least 1 Audio File"

    def render_output(self):
        self.render_example(st.session_state)

    def render_example(self, state: dict):
        render_documents(state)
        text_outputs("**Transcription**", value=state.get("output_text"))

    def render_steps(self):
        pass

    def run(self, state: dict):
        # Parse Request
        request: TranslationPage.RequestModel = self.RequestModel.parse_obj(state)
        yield f"Running..."

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
