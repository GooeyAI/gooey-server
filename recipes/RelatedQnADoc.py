import typing

from pydantic import BaseModel

import gooey_ui as st
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import document_uploader
from daras_ai_v2.functional import map_parallel, apply_parallel
from daras_ai_v2.language_model import LargeLanguageModels
from daras_ai_v2.language_model_settings_widgets import language_model_settings
from daras_ai_v2.prompt_vars import prompt_vars_widget
from daras_ai_v2.query_generator import generate_final_search_query
from daras_ai_v2.search_ref import CitationStyles
from daras_ai_v2.serp_search import get_related_questions_from_serp_api
from daras_ai_v2.serp_search_locations import (
    serp_search_settings,
    SerpSearchLocation,
    SerpSearchType,
)
from daras_ai_v2.vector_search import render_sources_widget
from recipes.DocSearch import DocSearchPage, render_doc_search_step, EmptySearchResults
from recipes.GoogleGPT import render_output_with_refs, GoogleSearchMixin

DEFAULT_GOOGLE_GPT_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/assets/WEBSEARCH%20%2B%20CHATGPT.jpg"


class RelatedDocSearchResponse(DocSearchPage.ResponseModel):
    search_query: str


class RelatedQnADocPage(BasePage):
    title = '"People Also Ask" Answers from a Doc'
    workflow = Workflow.RELATED_QNA_MAKER_DOC
    slug_versions = ["related-qna-maker-doc"]

    price = 100

    sane_defaults = dict(
        citation_style=CitationStyles.number.name,
        dense_weight=1.0,
        serp_search_type=SerpSearchType.SEARCH,
        serp_search_location=SerpSearchLocation.UNITED_STATES,
    )

    class RequestModel(GoogleSearchMixin, DocSearchPage.RequestModel):
        pass

    class ResponseModel(BaseModel):
        final_search_query: str
        output_queries: list[RelatedDocSearchResponse]
        serp_results: dict

    def render_description(self) -> str:
        return "This workflow gets the related queries for your Google search, searches your custom domain and builds answers using the results and GPT."

    def render_form_v2(self):
        DocSearchPage.render_form_v2(self)

    def validate_form_v2(self):
        DocSearchPage.validate_form_v2(self)

    def render_output(self):
        render_qna_outputs(st.session_state, 300)

    def render_example(self, state: dict):
        st.write("**Search Query**")
        st.write("```properties\n" + state.get("search_query", "") + "\n```")
        site_filter = state.get("site_filter")
        if site_filter:
            st.write(f"**Site** \\\n{site_filter}")
        render_qna_outputs(state, 200, show_count=1)

    def render_settings(self):
        DocSearchPage.render_settings(self)

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
        final_search_query = st.session_state.get("final_search_query")
        if final_search_query:
            st.text_area(
                "**Final Search Query**", value=final_search_query, disabled=True
            )

        serp_results = st.session_state.get(
            "serp_results", st.session_state.get("scaleserp_results")
        )
        if serp_results:
            st.write("**Web Search Results**")
            st.json(serp_results)

        output_queries = st.session_state.get("output_queries", [])
        for i, result in enumerate(output_queries):
            st.write("---")
            st.write(f"##### {i + 1}. _{result.get('search_query')}_")
            render_doc_search_step(result)

    def run_v2(
        self,
        request: "RelatedQnADocPage.RequestModel",
        response: "RelatedQnADocPage.ResponseModel",
    ):
        query_instructions = (request.query_instructions or "").strip()
        if query_instructions:
            yield "Generating final search query..."
            response.final_search_query = generate_final_search_query(
                request=request, response=response, instructions=query_instructions
            )
        else:
            response.final_search_query = request.search_query

        yield "Googling Related Questions..."
        (
            response.serp_results,
            related_questions,
        ) = get_related_questions_from_serp_api(
            response.final_search_query,
            search_location=request.serp_search_location,
        )

        all_questions = [request.search_query] + related_questions[:9]

        response.output_queries = []
        yield from apply_parallel(
            lambda ques: run_doc_search(request.copy(), ques, response.output_queries),
            all_questions,
            max_workers=4,
            message=f"Generating answers using {LargeLanguageModels[request.selected_model].value}...",
        )
        if not response.output_queries:
            raise EmptySearchResults(response.final_search_query)


def run_doc_search(
    request: DocSearchPage.RequestModel,
    related_question: str,
    outputs: list[RelatedDocSearchResponse],
):
    response = RelatedDocSearchResponse.construct()
    request.search_query = related_question
    response.search_query = related_question
    try:
        for _ in DocSearchPage().run_v2(request, response):
            pass
    except EmptySearchResults:
        return None
    outputs.append(response)


def render_qna_outputs(state, height, show_count=None):
    output_queries = state.get("output_queries", [])
    for output in output_queries[:show_count]:
        output_text = output.get("output_text", [])
        if not output_text:
            continue
        references = output.get("references", [])
        st.write(f"**{output.get('search_query')}**")
        render_output_with_refs(
            {"output_text": output_text, "references": references}, height
        )
        render_sources_widget(references)
        st.write("---")
