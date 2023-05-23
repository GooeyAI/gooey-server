import typing
from itertools import chain

import streamlit as st
from pydantic import BaseModel

from daras_ai_v2.GoogleGPT import GoogleGPTPage
from daras_ai_v2.base import BasePage
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.google_search import call_scaleserp
from daras_ai_v2.language_model import LargeLanguageModels
from daras_ai_v2.language_model_settings_widgets import language_model_settings
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.scaleserp_location_picker_widget import scaleserp_location_picker
from daras_ai_v2.search_ref import render_text_with_refs

DEFAULT_GOOGLE_GPT_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/assets/WEBSEARCH%20%2B%20CHATGPT.jpg"


class RelatedQuery(GoogleGPTPage.ResponseModel):
    search_query: str


class RelatedQnAPage(BasePage):
    title = "Realted QnA"
    slug_versions = ["related-qna-maker"]

    price = 175

    sane_defaults = dict(
        search_query="rugs",
        keywords="outdoor rugs,8x10 rugs,rug sizes,checkered rugs,5x7 rugs",
        title="Ruggable",
        company_url="https://ruggable.com",
        scaleserp_search_field="organic_results",
        scaleserp_locations=["United States"],
        enable_html=False,
        selected_model=LargeLanguageModels.text_davinci_003.name,
        sampling_temperature=0.8,
        max_tokens=1024,
        num_outputs=1,
        quality=1.0,
        max_search_urls=10,
        task_instructions="I will give you a URL and focus keywords and using the high ranking content from the google search results below you will write 500 words for the given url.",
        avoid_repetition=True,
        enable_crosslinks=False,
        seed=42,
        # enable_blog_mode=False,
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

    class ResponseModel(BaseModel):
        scaleserp_results: dict
        output_queries: list[RelatedQuery]

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
        render_outputs(st.session_state, 300)

    def render_example(self, state: dict):
        st.write("**Search Query**")
        st.write("```properties\n" + state.get("search_query", "") + "\n```")
        site_filter = state.get("site_filter")
        if site_filter:
            st.write(f"**Site** \\\n{site_filter}")
        render_outputs(state, 200)

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
        from recipes.VideoBots import VideoBotsPage
        from recipes.SocialLookupEmail import SocialLookupEmailPage

        return [
            DocSearchPage,
            SEOSummaryPage,
            VideoBotsPage,
            SocialLookupEmailPage,
        ]

    def preview_image(self, state: dict) -> str | None:
        return DEFAULT_GOOGLE_GPT_META_IMG

    def preview_description(self, state: dict) -> str:
        return "Like Bing + ChatGPT or perplexity.ai, this workflow queries Google and then summarizes the results (with citations!) using an editable GPT3 script.  Filter  results to your own website so users can ask anything and get answers based only on your site's pages."

    def render_usage_guide(self):
        youtube_video("mcscNaUIosA")

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
        st.write(st.session_state.get("output_queries", []))

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: RelatedQnAPage.RequestModel = self.RequestModel.parse_obj(state)
        search_query = request.search_query
        yield "Googling Related Questions..."
        state["scaleserp_results"] = scaleserp_results_rq = call_scaleserp(
            search_query,
            include_fields="related_questions",
            location=",".join(request.scaleserp_locations),
        )
        state["output_queries"] = output_queries = []
        output_queries: list[RelatedQuery]

        def run_google_gpt(related_question: dict) -> RelatedQuery:
            search_query_rq = related_question.get("question")
            yield f"Running for {search_query_rq}..."
            gpt_run_state = state
            gpt_run_state["search_query"] = search_query_rq
            yield from GoogleGPTPage().run(gpt_run_state)
            gpt_resp = RelatedQuery.parse_obj(gpt_run_state).dict()
            gpt_resp["search_query"] = search_query_rq
            output_queries.append(gpt_resp)

        outputs = map_parallel(
            run_google_gpt,
            scaleserp_results_rq.get("related_questions", []),
            max_workers=4,
        )
        yield from chain(*outputs)


def render_outputs(state, height):
    output_queries = state.get("output_queries", [])
    if output_queries:
        for output in output_queries:
            output_text = output.get("output_text", [])
            if output_text:
                st.write(f"**{output.get('search_query')}**")

                st.write("**Answer**")
            for text in output_text:
                references = output.get("references", [])

                html = render_text_with_refs(text, references)
                st.write(
                    # language=html
                    f"""<div style="max-height: {height}px;" class="gooey-output-text"><p>{html}</p></div>""",
                    unsafe_allow_html=True,
                )

            with st.expander("Sources"):
                for idx, ref in enumerate(output.get("references", [])):
                    st.write(
                        f"{idx + 1}. [{ref['title']}]({ref['url']}) \\\n*{ref['snippet']}*"
                    )
