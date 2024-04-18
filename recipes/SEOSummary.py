import random
import re
import typing

import readability
import requests
from furl import furl
from html_sanitizer import Sanitizer
from pydantic import BaseModel

import gooey_ui as st
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.exceptions import raise_for_status
from daras_ai_v2.fake_user_agents import FAKE_USER_AGENTS
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.language_model import (
    run_language_model,
    calc_gpt_tokens,
    LargeLanguageModels,
)
from daras_ai_v2.language_model_settings_widgets import language_model_settings
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.scrollable_html_widget import scrollable_html
from daras_ai_v2.serp_search import get_links_from_serp_api
from daras_ai_v2.serp_search_locations import (
    serp_search_settings,
    SerpSearchLocation,
    SerpSearchType,
)
from daras_ai_v2.settings import EXTERNAL_REQUEST_TIMEOUT_SEC
from recipes.GoogleGPT import GoogleSearchMixin

KEYWORDS_SEP = re.compile(r"[\n,]")

STOP_SEQ = "$" * 10
SEO_SUMMARY_DEFAULT_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/13d3ab1e-9457-11ee-98a6-02420a0001c9/SEO.jpg.png"

BANNED_HOSTS = [
    # youtube generally returns garbage
    "www.youtube.com",
    "youtube.com",
    "youtu.be",
]

sanitizer = Sanitizer(
    # https://github.com/matthiask/html-sanitizer/#settings
    settings={
        # don't really need any HTML attributes (e.g. href is useless because GPT doesn't know its URLs)
        "attributes": {},
    },
)


class SEOSummaryPage(BasePage):
    title = "Create a perfect SEO-optimized Title & Paragraph"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/85f38b42-88d6-11ee-ad97-02420a00016c/Create%20SEO%20optimized%20content%20option%202.png.png"
    workflow = Workflow.SEO_SUMMARY
    slug_versions = ["SEOSummary", "seo-paragraph-generator"]

    def preview_image(self, state: dict) -> str | None:
        return SEO_SUMMARY_DEFAULT_META_IMG

    def preview_description(self, state: dict) -> str:
        return "Input a Google search query + your website & keywords to get AI search engine optimized content. This workflow parses the current top ranked sites and generates the best page summary for your site using OpenAI’s GPT3."

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
        # enable_blog_mode=False,
    )

    class RequestModel(GoogleSearchMixin, BaseModel):
        search_query: str
        keywords: str
        title: str
        company_url: str

        task_instructions: str | None

        enable_html: bool | None

        selected_model: (
            typing.Literal[tuple(e.name for e in LargeLanguageModels)] | None
        )
        sampling_temperature: float | None
        max_tokens: int | None
        num_outputs: int | None
        quality: float | None
        avoid_repetition: bool | None

        max_search_urls: int | None

        enable_crosslinks: bool | None
        # generate_lead_image: bool | None
        # enable_blog_mode: bool | None

        seed: int | None

    class ResponseModel(BaseModel):
        output_content: list[str]

        serp_results: dict
        search_urls: list[str]
        summarized_urls: list[dict]
        final_prompt: str

    def related_workflows(self):
        from recipes.SocialLookupEmail import SocialLookupEmailPage
        from recipes.GoogleImageGen import GoogleImageGenPage
        from recipes.DocSearch import DocSearchPage
        from recipes.GoogleGPT import GoogleGPTPage

        return [
            GoogleGPTPage,
            DocSearchPage,
            SocialLookupEmailPage,
            GoogleImageGenPage,
        ]

    def render_usage_guide(self):
        youtube_video("8VDYTYWhOaw")

    def render_description(self):
        st.write(
            """
        This workflow is designed to make it incredibly easy to create a webpage that Google's search engine will rank well. 

It takes as inputs:
* The **search query** for which you'd like your page to be highly listed
* **Website name** - the name of your website or company
* **Website URL** - your site URL
* Focus **keywords** - any additional keywords that the workflow should include as it builds your page's content

How It Works:
1. Looks up the top 10 ranked sites for your search query
2. Parses their title, description and page content
3. Takes the parsed content + your site's URL, name and keywords to train a GPT3 script to build your page's suggested content.

SearchSEO > Page Parsing > GPT3
        """
        )

    def render_form_v2(self):
        st.write("#### Inputs")
        st.text_input("Google Search Query", key="search_query")
        st.text_input("Website Name", key="title")
        st.text_input("Website URL", key="company_url")
        st.text_area("Focus Keywords *(optional)*", key="keywords")

    def validate_form_v2(self):
        assert st.session_state["search_query"], "Please provide Google Search Query"
        assert st.session_state["title"], "Please provide Website Name"
        assert st.session_state["company_url"], "Please provide Website URL"
        # assert st.session_state["keywords"], "Please provide Focus Keywords"

    def render_settings(self):
        st.text_area(
            "### Task Instructions",
            key="task_instructions",
            height=300,
        )

        # st.checkbox("Blog Generator Mode", key="enable_blog_mode")
        st.checkbox("Enable Internal Cross-Linking", key="enable_crosslinks")
        st.checkbox("Enable HTML Formatting", key="enable_html")

        language_model_settings()

        st.write("---")

        serp_search_settings()

    def render_output(self):
        output_content = st.session_state.get("output_content")
        if output_content:
            st.write("#### Generated Content")
            for idx, text in enumerate(output_content):
                if st.session_state.get("enable_html"):
                    scrollable_html(text)
                else:
                    st.text_area(
                        f"output {idx}",
                        label_visibility="collapsed",
                        value=text,
                        height=300,
                        disabled=True,
                    )

        else:
            st.div()

    def render_steps(self):
        col1, col2 = st.columns(2)

        with col1:
            serp_results = st.session_state.get(
                "serp_results", st.session_state.get("scaleserp_results")
            )
            if serp_results:
                st.write("**Web Search Results**")
                st.json(serp_results)

        with col2:
            search_urls = st.session_state.get("search_urls")
            if search_urls:
                st.write("**Search URLs**")
                st.json(search_urls, expanded=False)
            else:
                st.div()

        summarized_urls = st.session_state.get("summarized_urls")
        if summarized_urls:
            st.write("**Summarized URLs**")
            st.json(summarized_urls, expanded=False)
        else:
            st.div()

        final_prompt = st.session_state.get("final_prompt")
        if final_prompt:
            st.text_area(
                "Final Prompt",
                value=final_prompt,
                height=400,
                disabled=True,
            )
        else:
            st.div()

    def render_example(self, state: dict):
        st.write(
            f"""
            Search Query `{state.get('search_query', '')}` \\
            Company Name `{state.get('title', '')}` \\
            Company URL `{state.get('company_url', '')}` \\
            Focus Keywords `{state.get('keywords', '')}`
            """
        )

        output_content = state.get("output_content")
        if output_content:
            if state.get("enable_html"):
                scrollable_html(output_content[0], height=300)
            else:
                st.text_area(
                    "Generated Content",
                    value=output_content[0],
                    height=200,
                    disabled=True,
                )

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: SEOSummaryPage.RequestModel = self.RequestModel.parse_obj(state)

        yield "Googling..."

        serp_results, links = get_links_from_serp_api(
            request.search_query,
            search_type=request.serp_search_type,
            search_location=request.serp_search_location,
        )
        state["serp_results"] = serp_results
        state["search_urls"] = [it.url for it in links]

        yield from _gen_final_prompt(request, state)

        yield f"Generating content using {LargeLanguageModels[request.selected_model].value}..."

        output_content = _run_lm(request, state["final_prompt"])

        if request.enable_crosslinks:
            yield "Cross-linking keywords..."
            output_content = _crosslink_keywords(output_content, request)

        state["output_content"] = output_content


def _crosslink_keywords(output_content, request):
    relevant_keywords = []

    for text in output_content:
        for keyword in KEYWORDS_SEP.split(request.keywords):
            keyword = keyword.strip()
            if not keyword:
                continue
            escaped = re.escape(keyword)
            if not re.search(pattern=escaped, string=text, flags=re.IGNORECASE):
                continue
            relevant_keywords.append(keyword)

    if not relevant_keywords:
        return output_content

    host = furl(request.company_url).host

    all_results = map_parallel(
        lambda keyword: get_links_from_serp_api(
            f"site:{host} {keyword}",
            search_type=request.serp_search_type,
            search_location=request.serp_search_location,
        )[1],
        relevant_keywords,
    )

    for keyword, results in zip(relevant_keywords, all_results):
        try:
            href = results[0].url
        except (IndexError, KeyError):
            continue

        escaped = re.escape(keyword)
        for idx, text in enumerate(output_content):
            output_content[idx] = re.sub(
                pattern=escaped,
                repl=f'<a href="{href}">{keyword}</a>',
                string=text,
                flags=re.IGNORECASE,
            )

    return output_content


def _run_lm(request: SEOSummaryPage.RequestModel, final_prompt: str) -> list[str]:
    return run_language_model(
        model=request.selected_model,
        quality=request.quality,
        num_outputs=request.num_outputs,
        temperature=request.sampling_temperature,
        prompt=final_prompt,
        max_tokens=request.max_tokens,
        stop=[STOP_SEQ],
        avoid_repetition=request.avoid_repetition,
    )


def _gen_final_prompt(
    request: SEOSummaryPage.RequestModel,
    state: dict,
) -> str:
    state["summarized_urls"] = summarized_urls = []

    padded_stop_seq = f"\n\n{STOP_SEQ}\n\n"

    end_input_prompt = "\n".join(
        [
            "Rank: 1",
            "Company Name: " + request.title,
            "Company URL: " + request.company_url,
            "Topic: " + request.search_query,
            "Focus Keywords: " + request.keywords,
            "Article: " + padded_stop_seq,
        ]
    )

    max_allowed_tokens = (
        LargeLanguageModels[request.selected_model].context_window
        - request.max_tokens
        - calc_gpt_tokens(end_input_prompt)
    )

    state["final_prompt"] = request.task_instructions.strip() + "\n\n"

    for idx, url in enumerate(state["search_urls"]):
        yield f"Summarizing {url}..."

        summary_dict = _summarize_url(url, request.enable_html)
        if not summary_dict:
            continue

        summarized_urls.append(summary_dict)

        clean_summary = summary_dict["summary"].replace(STOP_SEQ, "")
        padded_summary = padded_stop_seq + clean_summary + padded_stop_seq

        next_prompt_part = "\n".join(
            [
                "Rank: " + str(idx + 1),
                "Company Name: " + summary_dict["title"],
                "Company URL: " + summary_dict["url"],
                "Article: " + padded_summary,
            ]
        )

        # used too many tokens, abort!
        if (
            calc_gpt_tokens(state["final_prompt"] + next_prompt_part)
            > max_allowed_tokens
        ):
            continue

        state["final_prompt"] += next_prompt_part

    # add inputs
    state["final_prompt"] += end_input_prompt


def _summarize_url(url: str, enable_html: bool):
    from lxml import etree

    try:
        title, summary = _call_summarize_url(url)
    except (requests.RequestException, etree.LxmlError):
        return None

    title = html_to_text(title)
    if enable_html:
        summary = sanitizer.sanitize(summary)
    else:
        summary = html_to_text(summary)

    title = title.strip()
    summary = summary.strip()

    if not summary:
        return None

    return {
        "url": url,
        "title": title,
        "summary": summary,
    }


def html_to_text(text):
    from bs4 import BeautifulSoup

    return BeautifulSoup(text, "html.parser").get_text(separator=" ", strip=True)


def _call_summarize_url(url: str) -> (str, str):
    r = requests.get(
        url,
        headers={"User-Agent": random.choice(FAKE_USER_AGENTS)},
        timeout=EXTERNAL_REQUEST_TIMEOUT_SEC,
    )
    raise_for_status(r)
    doc = readability.Document(r.text)
    return doc.title(), doc.summary()
