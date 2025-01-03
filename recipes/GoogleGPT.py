import typing

from furl import furl
from pydantic import BaseModel

import gooey_gui as gui
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import (
    query_instructions_widget,
    doc_search_advanced_settings,
)
from daras_ai_v2.embedding_model import EmbeddingModels
from daras_ai_v2.language_model import (
    run_language_model,
    LargeLanguageModels,
)
from daras_ai_v2.language_model_settings_widgets import (
    language_model_settings,
    language_model_selector,
    LanguageModelSettings,
)
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.variables_widget import render_prompt_vars
from daras_ai_v2.query_generator import generate_final_search_query
from daras_ai_v2.search_ref import (
    SearchReference,
    render_output_with_refs,
)
from daras_ai_v2.serp_search import get_links_from_serp_api
from daras_ai_v2.serp_search_locations import (
    GoogleSearchMixin,
    serp_search_settings,
    SerpSearchLocation,
    SerpSearchType,
)
from daras_ai_v2.vector_search import render_sources_widget
from recipes.DocSearch import (
    DocSearchRequest,
    references_as_prompt,
    get_top_k_references,
    EmptySearchResults,
)

DEFAULT_GOOGLE_GPT_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/85ed60a2-9405-11ee-9747-02420a0001ce/Web%20search%20GPT.jpg.png"


class GoogleGPTPage(BasePage):
    title = "Web Search + GPT3"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/28649544-9406-11ee-bba3-02420a0001cc/Websearch%20GPT%20option%202.png.png"
    workflow = Workflow.GOOGLE_GPT
    slug_versions = ["google-gpt"]

    price = 175

    sane_defaults = dict(
        search_query="rugs",
        keywords="outdoor rugs,8x10 rugs,rug sizes,checkered rugs,5x7 rugs",
        title="Ruggable",
        company_url="https://ruggable.com",
        serp_search_type=SerpSearchType.SEARCH,
        serp_search_location=SerpSearchLocation.UNITED_STATES,
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

    class RequestModelBase(BasePage.RequestModel):
        search_query: str
        site_filter: str

        task_instructions: str | None
        query_instructions: str | None

        selected_model: (
            typing.Literal[tuple(e.name for e in LargeLanguageModels)] | None
        )

        max_search_urls: int | None

        max_references: int | None
        max_context_words: int | None
        scroll_jump: int | None

        embedding_model: typing.Literal[tuple(e.name for e in EmbeddingModels)] | None
        dense_weight: float | None = DocSearchRequest.__fields__[
            "dense_weight"
        ].field_info

    class RequestModel(GoogleSearchMixin, LanguageModelSettings, RequestModelBase):
        pass

    class ResponseModel(BaseModel):
        output_text: list[str]

        serp_results: dict

        references: list[SearchReference]
        final_prompt: str

        final_search_query: str | None

    def render_form_v2(self):
        gui.text_area("#### Google Search Query", key="search_query")
        gui.text_input("Search on a specific site *(optional)*", key="site_filter")

    def validate_form_v2(self):
        assert gui.session_state.get(
            "search_query", ""
        ).strip(), "Please enter a search query"

    def render_output(self):
        render_output_with_refs(gui.session_state)

        refs = gui.session_state.get("references", [])
        render_sources_widget(refs)

    def render_example(self, state: dict):
        gui.write("**Search Query**")
        gui.write("```properties\n" + state.get("search_query", "") + "\n```")
        site_filter = state.get("site_filter")
        if site_filter:
            gui.write(f"**Site** \\\n{site_filter}")
        render_output_with_refs(state, 200)

    def render_settings(self):
        gui.text_area(
            "### Task Instructions",
            key="task_instructions",
            height=300,
        )
        gui.write("---")
        selected_model = language_model_selector()
        language_model_settings(selected_model)
        gui.write("---")
        serp_search_settings()
        gui.write("---")
        gui.write("##### 🔎 Document Search Settings")
        query_instructions_widget()
        gui.write("---")
        doc_search_advanced_settings()

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
        final_search_query = gui.session_state.get("final_search_query")
        if final_search_query:
            gui.text_area(
                "**Final Search Query**", value=final_search_query, disabled=True
            )

        serp_results = gui.session_state.get(
            "serp_results", gui.session_state.get("scaleserp_results")
        )
        if serp_results:
            gui.write("**Web Search Results**")
            gui.json(serp_results)

        final_prompt = gui.session_state.get("final_prompt")
        if final_prompt:
            gui.text_area(
                "**Final Prompt**",
                value=final_prompt,
                height=400,
                disabled=True,
            )

        output_text: list = gui.session_state.get("output_text", [])
        for idx, text in enumerate(output_text):
            gui.text_area(
                "**Output Text**",
                help=f"output {idx}",
                disabled=True,
                value=text,
            )

        references = gui.session_state.get("references", [])
        if references:
            gui.write("**References**")
            gui.json(references)

    def run_v2(
        self,
        request: "GoogleGPTPage.RequestModel",
        response: "GoogleGPTPage.ResponseModel",
    ):
        model = LargeLanguageModels[request.selected_model]

        query_instructions = (request.query_instructions or "").strip()
        if query_instructions:
            yield "Generating final search query..."
            response.final_search_query = generate_final_search_query(
                request=request, response=response, instructions=query_instructions
            )
        else:
            response.final_search_query = request.search_query

        yield "Googling..."
        if request.site_filter:
            f = furl(request.site_filter)
            response.final_search_query = (
                f"site:{f.host}{f.path} {response.final_search_query}"
            )
        response.serp_results, links = get_links_from_serp_api(
            response.final_search_query,
            search_type=request.serp_search_type,
            search_location=request.serp_search_location,
        )
        # extract links & their corresponding titles
        link_titles = {item.url: f"{item.title} | {item.snippet}" for item in links}
        if not link_titles:
            raise EmptySearchResults(response.final_search_query)

        # run vector search on links
        response.references = yield from get_top_k_references(
            DocSearchRequest.parse_obj(
                {
                    **request.dict(),
                    "documents": list(link_titles.keys()),
                    "search_query": request.search_query,
                },
            ),
            is_user_url=False,
            current_user=self.request.user,
        )

        # add pretty titles to references

        for ref in response.references:
            key = furl(ref["url"]).remove(fragment=True).url
            ref["title"] = link_titles.get(key, "")

        # empty search result, abort!
        if not response.references:
            raise EmptySearchResults(request.search_query)

        response.final_prompt = ""
        # add search results to the prompt
        response.final_prompt += references_as_prompt(response.references) + "\n\n"
        # add task instructions
        task_instructions = render_prompt_vars(
            prompt=request.task_instructions, state=request.dict() | response.dict()
        )
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
            response_format_type=request.response_format_type,
        )
