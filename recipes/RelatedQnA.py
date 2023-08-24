import typing

from pydantic import BaseModel

import gooey_ui as st
from bots.models import Workflow
from daras_ai_v2.GoogleGPT import GoogleGPTPage
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import doc_search_settings
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.google_search import call_scaleserp_rq
from daras_ai_v2.language_model import LargeLanguageModels
from daras_ai_v2.language_model_settings_widgets import language_model_settings
from daras_ai_v2.scaleserp_location_picker_widget import scaleserp_location_picker
from recipes.DocSearch import render_doc_search_step
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
    )

    class RequestModel(BaseModel):
        search_query: str
        site_filter: str

        task_instructions: str | None

        selected_model: typing.Literal[
            tuple(e.name for e in LargeLanguageModels)
        ] | None
        avoid_repetition: bool | None
        num_outputs: int | None
        quality: float | None
        max_tokens: int | None
        sampling_temperature: float | None

        max_search_urls: int | None

        scaleserp_search_field: str | None
        scaleserp_locations: list[str] | None

        max_references: int | None
        max_context_words: int | None
        scroll_jump: int | None

    class ResponseModel(BaseModel):
        output_queries: list[RelatedGoogleGPTResponse]
        scaleserp_results: dict

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
        doc_search_settings(asr_allowed=False)

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
        col1, col2 = st.columns(2)

        with col1:
            scaleserp_results = st.session_state.get("scaleserp_results")
            if scaleserp_results:
                st.write("**ScaleSERP Results**")
                st.json(scaleserp_results, expanded=False)

        output_queries = st.session_state.get("output_queries", [])
        for i, result in enumerate(output_queries):
            st.write("---")
            st.write(f"##### {i+1}. _{result.get('search_query')}_")
            scaleserp_results = result.get("scaleserp_results")
            if scaleserp_results:
                st.write("**ScaleSERP Results**")
                st.json(scaleserp_results, expanded=False)
            render_doc_search_step(
                result.get("final_prompt", ""),
                result.get("output_text", []),
                result.get("references", []),
            )

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: RelatedQnAPage.RequestModel = self.RequestModel.parse_obj(state)
        search_query = request.search_query

        yield "Googling Related Questions..."
        scaleserp_results, related_questions = call_scaleserp_rq(
            search_query,
            location=",".join(request.scaleserp_locations),
        )
        # add the original search query
        related_questions.insert(0, search_query)
        # save the results
        state["scaleserp_results"] = scaleserp_results
        state["related_questions"] = related_questions

        yield f"Generating answers using {LargeLanguageModels[request.selected_model].value}..."
        state["output_queries"] = map_parallel(
            lambda ques: run_google_gpt(state.copy(), ques),
            related_questions,
            max_workers=4,
        )


def run_google_gpt(state: dict, related_question: str):
    state["search_query"] = related_question
    for _ in GoogleGPTPage().run(state):
        pass
    return RelatedGoogleGPTResponse.parse_obj(state).dict()
