import datetime
import typing

import jinja2
from furl import furl
from pydantic import BaseModel

import gooey_ui as st
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import doc_search_settings
from daras_ai_v2.google_search import call_scaleserp
from daras_ai_v2.language_model import (
    run_language_model,
    LargeLanguageModels,
    model_max_tokens,
)
from daras_ai_v2.language_model_settings_widgets import language_model_settings
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.scaleserp_location_picker_widget import scaleserp_location_picker
from daras_ai_v2.search_ref import (
    SearchReference,
    render_output_with_refs,
)
from daras_ai_v2.vector_search import render_sources_widget
from recipes.DocSearch import (
    DocSearchRequest,
    references_as_prompt,
    get_top_k_references,
)

DEFAULT_GOOGLE_GPT_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/assets/WEBSEARCH%20%2B%20CHATGPT.jpg"


class GoogleGPTPage(BasePage):
    title = "Web Search + GPT3"
    workflow = Workflow.GOOGLE_GPT
    slug_versions = ["google-gpt"]

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
        max_references=4,
        max_context_words=200,
        scroll_jump=5,
        dense_weight=1.0,
    )

    class RequestModel(BaseModel):
        search_query: str
        site_filter: str

        task_instructions: str | None
        query_instructions: str | None

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

        dense_weight: float | None = DocSearchRequest.__fields__[
            "dense_weight"
        ].field_info

    class ResponseModel(BaseModel):
        output_text: list[str]

        scaleserp_results: dict
        # search_urls: list[str]
        # summarized_urls: list[dict]
        references: list[SearchReference]
        final_prompt: str

        final_search_query: str | None

    def render_form_v2(self):
        st.text_area("##### Google Search Query", key="search_query")
        st.text_input("Search on a specific site *(optional)*", key="site_filter")

    def validate_form_v2(self):
        assert st.session_state.get(
            "search_query", ""
        ).strip(), "Please enter a search query"

    def render_output(self):
        render_output_with_refs(st.session_state, 300)

        refs = st.session_state.get("references", [])
        render_sources_widget(refs)

    def render_example(self, state: dict):
        st.write("**Search Query**")
        st.write("```properties\n" + state.get("search_query", "") + "\n```")
        site_filter = state.get("site_filter")
        if site_filter:
            st.write(f"**Site** \\\n{site_filter}")
        render_output_with_refs(state, 200)

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
        final_search_query = st.session_state.get("final_search_query")
        if final_search_query:
            st.text_area(
                "**Final Search Query**", value=final_search_query, disabled=True
            )

        scaleserp_results = st.session_state.get("scaleserp_results")
        if scaleserp_results:
            st.write("**ScaleSERP Results**")
            st.json(scaleserp_results)

        final_prompt = st.session_state.get("final_prompt")
        if final_prompt:
            st.text_area(
                "**Final Prompt**",
                value=final_prompt,
                height=400,
                disabled=True,
            )

        output_text: list = st.session_state.get("output_text", [])
        for idx, text in enumerate(output_text):
            st.text_area(
                f"**Output Text**",
                help=f"output {idx}",
                disabled=True,
                value=text,
                height=200,
            )

        references = st.session_state.get("references", [])
        if references:
            st.write("**References**")
            st.json(references)

    def run_v2(
        self,
        request: "GoogleGPTPage.RequestModel",
        response: "GoogleGPTPage.ResponseModel",
    ):
        model = LargeLanguageModels[request.selected_model]

        query_instructions = (request.query_instructions or "").strip()
        if query_instructions:
            query_instructions = jinja2.Template(query_instructions).render(
                **request.dict()
            )
            final_search_query = run_language_model(
                model=request.selected_model,
                prompt=query_instructions,
                max_tokens=model_max_tokens[model] // 2,
                quality=request.quality,
                temperature=request.sampling_temperature,
                avoid_repetition=request.avoid_repetition,
            )[0]
            response.final_search_query = (
                final_search_query.strip().strip('"').strip("'")
            )
        else:
            response.final_search_query = request.search_query

        yield "Googling..."
        if request.site_filter:
            f = furl(request.site_filter)
            serp_search_query = f"site:{f.host}{f.path} {response.final_search_query}"
        else:
            serp_search_query = response.final_search_query
        response.scaleserp_results = call_scaleserp(
            serp_search_query,
            include_fields=request.scaleserp_search_field,
            location=",".join(request.scaleserp_locations),
        )
        # extract links & their corresponding titles
        link_titles = {
            furl(item["link"])
            .remove(fragment=True)
            .url: f'{item.get("title", "")} | {item.get("snippet", "")}'
            for item in response.scaleserp_results.get(
                request.scaleserp_search_field, []
            )
            if item and item.get("link")
        }

        # run vector search on links
        response.references = yield from get_top_k_references(
            DocSearchRequest.parse_obj(
                {
                    **request.dict(),
                    "documents": list(link_titles.keys()),
                    "search_query": response.final_search_query,
                },
            ),
        )
        # add pretty titles to references
        for ref in response.references:
            key = furl(ref["url"]).remove(fragment=True).url
            ref["title"] = link_titles.get(key, "")

        # empty search result, abort!
        if not response.references:
            raise ValueError(
                f"Your search - {request.search_query} - did not match any documents."
            )

        response.final_prompt = ""
        # add time to instructions
        utcnow = datetime.datetime.utcnow().strftime("%B %d, %Y %H:%M:%S %Z")
        task_instructions = request.task_instructions.replace(
            "{{ datetime.utcnow }}", utcnow
        )
        # add search results to the prompt
        response.final_prompt += references_as_prompt(response.references) + "\n\n"
        # add task instructions
        response.final_prompt += task_instructions.strip() + "\n\n"
        # add the question
        response.final_prompt += f"Question: {request.search_query}\nAnswer:"

        yield f"Generating answer using {model.value}..."
        response.output_text = run_language_model(
            model=request.selected_model,
            quality=request.quality,
            num_outputs=request.num_outputs,
            temperature=request.sampling_temperature,
            prompt=response.final_prompt,
            max_tokens=request.max_tokens,
            avoid_repetition=request.avoid_repetition,
        )
