from pydantic import BaseModel

import gooey_ui as st
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import doc_search_settings
from daras_ai_v2.functional import apply_parallel
from daras_ai_v2.language_model import (
    LargeLanguageModels,
)
from daras_ai_v2.language_model_settings_widgets import language_model_settings
from daras_ai_v2.query_generator import generate_final_search_query
from daras_ai_v2.serp_search import get_related_questions_from_serp_api
from daras_ai_v2.serp_search_locations import (
    serp_search_settings,
    SerpSearchLocation,
    SerpSearchType,
)
from recipes.DocSearch import render_doc_search_step, EmptySearchResults
from recipes.GoogleGPT import GoogleGPTPage
from recipes.RelatedQnADoc import render_qna_outputs

DEFAULT_GOOGLE_GPT_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/assets/WEBSEARCH%20%2B%20CHATGPT.jpg"


class RelatedGoogleGPTResponse(GoogleGPTPage.ResponseModel):
    search_query: str


class RelatedQnAPage(BasePage):
    title = 'Generate "People Also Ask" SEO Content '
    workflow = Workflow.RELATED_QNA_MAKER
    slug_versions = ["related-qna-maker"]

    price = 75

    sane_defaults = dict(
        max_references=4,
        max_context_words=200,
        scroll_jump=5,
        dense_weight=1.0,
        serp_search_type=SerpSearchType.SEARCH,
        serp_search_location=SerpSearchLocation.UNITED_STATES,
    )

    class RequestModel(GoogleGPTPage.RequestModel):
        pass

    class ResponseModel(BaseModel):
        final_search_query: str
        output_queries: list[RelatedGoogleGPTResponse]
        serp_results: dict

    def render_description(self) -> str:
        return "This workflow gets the related queries for your Google search, searches your custom domain and builds answers using the results and GPT."

    def render_form_v2(self):
        st.text_input("##### Google Search Query", key="search_query")
        st.text_input("Search on a specific site *(optional)*", key="site_filter")

    def validate_form_v2(self):
        assert st.session_state.get(
            "search_query", ""
        ).strip(), "Please enter a search query"

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

        doc_search_settings(asr_allowed=False)
        st.write("---")

        serp_search_settings()

    def related_workflows(self) -> list:
        from recipes.SEOSummary import SEOSummaryPage
        from recipes.VideoBots import VideoBotsPage
        from recipes.SocialLookupEmail import SocialLookupEmailPage

        return [
            GoogleGPTPage,
            SEOSummaryPage,
            VideoBotsPage,
            SocialLookupEmailPage,
        ]

    def preview_description(self, state: dict) -> str:
        return 'Input your Google Search query and discover related Q&As that your audience is asking, so you can create content that is more relevant and engaging. This workflow finds the related queries (aka "People also ask") for your Google search, browses through the URL you provide for all related results from your query and finally, generates cited answers from those results. A great way to quickly improve your website\'s SEO rank if you already rank well for a given query.'

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
            st.write(f"##### {i+1}. _{result.get('search_query')}_")
            serp_results = result.get("serp_results", result.get("scaleserp_results"))
            if serp_results:
                st.write("**Web Search Results**")
                st.json(serp_results)
            render_doc_search_step(result)

    def run_v2(
        self,
        request: "RelatedQnAPage.RequestModel",
        response: "RelatedQnAPage.ResponseModel",
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
            lambda ques: run_google_gpt(request.copy(), ques, response.output_queries),
            all_questions,
            max_workers=4,
            message=f"Generating answers using {LargeLanguageModels[request.selected_model].value}...",
        )
        if not response.output_queries:
            raise EmptySearchResults(response.final_search_query)


def run_google_gpt(
    request: GoogleGPTPage.RequestModel,
    related_question: str,
    outputs: list[RelatedGoogleGPTResponse],
):
    response = RelatedGoogleGPTResponse.construct()
    request.search_query = related_question
    response.search_query = related_question
    try:
        for _ in GoogleGPTPage().run_v2(request, response):
            pass
    except EmptySearchResults:
        return
    outputs.append(response)
