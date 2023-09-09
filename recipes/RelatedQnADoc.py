import typing

from pydantic import BaseModel

import gooey_ui as st
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import document_uploader
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.language_model import LargeLanguageModels
from daras_ai_v2.language_model_settings_widgets import language_model_settings
from daras_ai_v2.search_ref import CitationStyles
from daras_ai_v2.serp_search import get_related_questions_from_serp_api
from daras_ai_v2.serp_search_locations import (
    serp_search_settings,
    SerpSearchLocation,
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
        serp_search_location=SerpSearchLocation.UNITED_STATES.value,
    )

    class RequestModel(GoogleSearchMixin, DocSearchPage.RequestModel):
        pass

    class ResponseModel(BaseModel):
        output_queries: list[RelatedDocSearchResponse]
        serp_results: dict

    def render_description(self) -> str:
        return "This workflow gets the related queries for your Google search, searches your custom domain and builds answers using the results and GPT."

    def render_form_v2(self):
        st.text_input("##### Search Query", key="search_query")
        document_uploader("##### Documents")

    def validate_form_v2(self):
        assert st.session_state.get(
            "search_query", ""
        ).strip(), "Please enter a search query"
        assert st.session_state.get("documents"), "Please provide at least 1 Document"

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
        st.text_area(
            "### Task Instructions",
            key="task_instructions",
            height=300,
        )

        language_model_settings()

        st.write("---")

        serp_search_settings()

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
            render_doc_search_step(
                result.get("final_prompt", ""),
                result.get("output_text", []),
                result.get("references", []),
            )

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: RelatedQnADocPage.RequestModel = self.RequestModel.parse_obj(state)
        search_query = request.search_query

        yield "Googling Related Questions..."
        serp_results, related_questions = get_related_questions_from_serp_api(
            search_query,
            search_location=request.serp_search_location,
        )
        state["serp_results"] = serp_results
        state["related_questions"] = related_questions

        all_queries = [search_query] + related_questions

        yield f"Generating answers using {LargeLanguageModels[request.selected_model].value}..."
        output_queries = map_parallel(
            lambda ques: run_doc_search(state.copy(), ques),
            all_queries,
            max_workers=4,
        )
        output_queries = list(filter(None, output_queries))
        if not output_queries:
            raise EmptySearchResults(search_query)
        state["output_queries"] = output_queries


def run_doc_search(state: dict, related_question: str):
    state["search_query"] = related_question
    try:
        for _ in DocSearchPage().run(state):
            pass
    except EmptySearchResults:
        return None
    return RelatedDocSearchResponse.parse_obj(state).dict()


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
