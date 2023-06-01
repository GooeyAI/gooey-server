import typing

import streamlit as st
from pydantic import BaseModel
from streamlit.runtime.uploaded_file_manager import UploadedFile

from daras_ai.image_input import upload_st_file
from daras_ai_v2.GoogleGPT import render_outputs
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import document_uploader
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.google_search import call_scaleserp
from daras_ai_v2.language_model import LargeLanguageModels
from daras_ai_v2.language_model_settings_widgets import language_model_settings
from daras_ai_v2.scaleserp_location_picker_widget import scaleserp_location_picker
from recipes.DocSearch import DocSearchPage, render_step

DEFAULT_GOOGLE_GPT_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/assets/WEBSEARCH%20%2B%20CHATGPT.jpg"


class RelatedQuery(DocSearchPage.ResponseModel):
    search_query: str


class RelatedQnADocPage(BasePage):
    title = '"People Also Ask" Answers from a Doc'
    slug_versions = ["related-qna-maker-doc"]

    price = 175

    class RequestModel(BaseModel):
        search_query: str
        documents: list[str] | None
        task_instructions: str | None

        selected_model: typing.Literal[
            tuple(e.name for e in LargeLanguageModels)
        ] | None
        avoid_repetition: bool | None
        num_outputs: int | None
        quality: float | None
        max_tokens: int | None
        max_references: int | None
        max_context_words: int | None
        scroll_jump: int | None

        sampling_temperature: float | None

        scaleserp_search_field: str | None
        scaleserp_locations: list[str] | None

    class ResponseModel(BaseModel):
        scaleserp_results: dict
        output_queries: list[RelatedQuery]

    def render_description(self) -> str:
        return "This workflow gets the related queries for your Google search, searches your custom domain and builds answers using the results and GPT."

    def render_form_v2(self):
        st.text_input("##### Search Query", key="search_query")
        document_uploader("##### Documents")

    def validate_form_v2(self):
        assert st.session_state.get(
            "search_query", ""
        ).strip(), "Please enter a search query"

        search_query = st.session_state.get("search_query", "").strip()
        assert search_query, "Please enter a Search Query"

        document_files: list[UploadedFile] | None = st.session_state.get(
            "__documents_files"
        )
        if document_files:
            uploaded = []
            for f in document_files:
                if f.name == "urls.txt":
                    uploaded.extend(f.getvalue().decode().splitlines())
                else:
                    uploaded.append(upload_st_file(f))
            st.session_state["documents"] = uploaded
        assert st.session_state.get("documents"), "Please provide at least 1 Document"

    def render_output(self):
        render_qna_outputs(st.session_state, 300)

    def render_example(self, state: dict):
        st.write("**Search Query**")
        st.write("```properties\n" + state.get("search_query", "") + "\n```")
        site_filter = state.get("site_filter")
        if site_filter:
            st.write(f"**Site** \\\n{site_filter}")
        render_qna_outputs(state, 200)

    def render_settings(self):
        st.text_area(
            "### Task Instructions",
            key="task_instructions",
            height=100,
        )

        language_model_settings()

        st.write("---")

        st.write("#### Search Tools")

        col1, col2 = st.columns(2)
        with col1:
            st.text_input(
                "**ScaleSERP [Search Property](https://www.scaleserp.com/docs/search-api/results/google/search)**",
                key="scaleserp_search_field",
            )
        with col2:
            st.number_input(
                label="""
                ###### Max Search URLs
                The maximum number of search URLs to consider as References
                """,
                key="max_search_urls",
                min_value=1,
                max_value=10,
            )
        scaleserp_location_picker()

    def related_workflows(self) -> list:
        from recipes.SEOSummary import SEOSummaryPage
        from recipes.DocSearch import DocSearchPage
        from recipes.RelatedQnA import RelatedQnAPage
        from recipes.CompareLLM import CompareLLMPage

        return [
            RelatedQnAPage,
            SEOSummaryPage,
            DocSearchPage,
            CompareLLMPage,
        ]

    def preview_description(self, state: dict) -> str:
        return 'This workflow finds the related queries (aka "People also ask") for a Google search, searches your doc, pdf or file (from a URL or via an upload) and then generates answers using vector DB results from your docs.'

    def render_steps(self):
        col1, col2 = st.columns(2)
        with col1:
            scaleserp_results = st.session_state.get("scaleserp_results")
            if scaleserp_results:
                st.write("**ScaleSERP Results**")
                st.json(scaleserp_results, expanded=False)
            else:
                st.empty()
        st.write("**Related Queries**")
        output_queries = st.session_state.get("output_queries", [])
        if output_queries:
            for output_query in output_queries:
                st.write(f"{output_query.get('search_query')}")
                render_step(
                    output_query.get("final_prompt"),
                    output_query.get("output_text", []),
                    output_query.get("references", []),
                )

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: RelatedQnADocPage.RequestModel = self.RequestModel.parse_obj(state)
        search_query = request.search_query
        yield "Googling Related Questions..."
        state["scaleserp_results"] = scaleserp_results_rq = call_scaleserp(
            search_query,
            include_fields="related_questions",
            location=",".join(request.scaleserp_locations),
        )
        related_questions = [
            search_query,  # add the original search query
            *[
                rq["question"]
                for rq in scaleserp_results_rq.get("related_questions", [])
            ],
        ]

        state["output_queries"] = output_queries = []
        output_queries: list[RelatedQuery]
        yield f"Generating answers using [{LargeLanguageModels[request.selected_model].value}]..."

        def run_doc_search(related_question: str):
            doc_run_state = state.copy()
            doc_run_state["search_query"] = related_question
            list(DocSearchPage().run(doc_run_state))
            doc_search_resp = RelatedQuery.parse_obj(doc_run_state).dict()
            doc_search_resp["search_query"] = related_question
            output_queries.append(doc_search_resp)

        map_parallel(
            run_doc_search,
            related_questions,
            max_workers=4,
        )


def render_qna_outputs(state, height):
    output_queries = state.get("output_queries", [])
    if output_queries:
        for output in output_queries:
            output_text = output.get("output_text", [])
            if output_text:
                st.write(f"**{output.get('search_query')}**")
                render_outputs({"output_text": output_text}, height)
