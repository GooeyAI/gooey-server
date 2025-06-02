from pydantic import BaseModel

import gooey_gui as gui
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.functional import apply_parallel
from daras_ai_v2.language_model import (
    LargeLanguageModels,
)
from daras_ai_v2.serp_search import get_related_questions_from_serp_api
from daras_ai_v2.serp_search_locations import (
    SerpSearchLocation,
    SerpSearchType,
)
from recipes.DocSearch import render_doc_search_step, EmptySearchResults
from recipes.GoogleGPT import GoogleGPTPage
from recipes.RelatedQnADoc import render_qna_outputs


class RelatedGoogleGPTResponse(GoogleGPTPage.ResponseModel):
    search_query: str


class RelatedQnAPage(BasePage):
    title = "Generate “People Also Ask” SEO Content "
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/37b0ba22-88d6-11ee-b549-02420a000167/People%20also%20ask.png.png"
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
        output_queries: list[RelatedGoogleGPTResponse]
        serp_results: dict

    def render_description(self) -> str:
        return "This workflow gets the related queries for your Google search, searches your custom domain and builds answers using the results and GPT."

    def render_form_v2(self):
        GoogleGPTPage.render_form_v2(self)

    def validate_form_v2(self):
        GoogleGPTPage.validate_form_v2(self)

    def render_steps(self):
        serp_results = gui.session_state.get(
            "serp_results", gui.session_state.get("scaleserp_results")
        )
        if serp_results:
            gui.write("**Web Search Results**")
            gui.json(serp_results)

        output_queries = gui.session_state.get("output_queries", [])
        for i, result in enumerate(output_queries):
            gui.write("---")
            gui.write(f"##### {i + 1}. _{result.get('search_query')}_")
            serp_results = result.get("serp_results", result.get("scaleserp_results"))
            if serp_results:
                gui.write("**Web Search Results**")
                gui.json(serp_results)
            render_doc_search_step(result)

    def render_output(self):
        render_qna_outputs(gui.session_state, 300)

    def render_run_preview_output(self, state: dict):
        gui.write("**Search Query**")
        gui.write("```properties\n" + state.get("search_query", "") + "\n```")
        site_filter = state.get("site_filter")
        if site_filter:
            gui.write(f"**Site** \\\n{site_filter}")
        render_qna_outputs(state, 200, show_count=1)

    def render_settings(self):
        GoogleGPTPage.render_settings(self)

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

    def run_v2(
        self,
        request: "RelatedQnAPage.RequestModel",
        response: "RelatedQnAPage.ResponseModel",
    ):
        yield "Googling Related Questions..."
        (
            response.serp_results,
            related_questions,
        ) = get_related_questions_from_serp_api(
            request.search_query,
            search_location=request.serp_search_location,
        )

        all_questions = [request.search_query] + related_questions[:9]

        response.output_queries = []
        yield from apply_parallel(
            lambda ques: run_google_gpt(
                request.model_copy(), ques, response.output_queries
            ),
            all_questions,
            max_workers=4,
            message=f"Generating answers using {LargeLanguageModels[request.selected_model].value}...",
        )
        if not response.output_queries:
            raise EmptySearchResults(request.search_query)


def run_google_gpt(
    request: GoogleGPTPage.RequestModel,
    related_question: str,
    outputs: list[RelatedGoogleGPTResponse],
):
    response = RelatedGoogleGPTResponse.model_construct()
    request.search_query = related_question
    response.search_query = related_question
    try:
        for _ in GoogleGPTPage().run_v2(request, response):
            pass
    except EmptySearchResults:
        return
    outputs.append(response)
