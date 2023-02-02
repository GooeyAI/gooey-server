import re
import typing
from functools import partial

import readability
import requests
import streamlit as st
from bs4 import BeautifulSoup
from furl import furl
from html_sanitizer import Sanitizer
from lxml import etree
from pydantic import BaseModel

from daras_ai_v2.base import BasePage
from daras_ai_v2.face_restoration import map_parallel
from daras_ai_v2.fake_user_agents import FAKE_USER_AGENTS
from daras_ai_v2.google_search import call_scaleserp
from daras_ai_v2.language_model import (
    run_language_model,
    GPT3_MAX_ALLOED_TOKENS,
    calc_gpt_tokens,
)
from daras_ai_v2.language_model_settings_widgets import language_model_settings
from daras_ai_v2.scrollable_html_widget import scrollable_html
from daras_ai_v2.settings import EXTERNAL_REQUEST_TIMEOUT_SEC
from daras_ai_v2.utils import random

KEYWORDS_SEP = re.compile(r"[\n,]")

STOP_SEQ = "$" * 10
SEO_SUMMARY_DEFAULT_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/assets/seo.png"

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
        scaleserp_search_field="organic_results",
        enable_html=False,
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
        keywords: str
        title: str
        company_url: str

        task_instructions: str | None

        scaleserp_search_field: str | None
        enable_html: bool | None

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

        scaleserp_results: dict
        search_urls: list[str]
        summarized_urls: list[dict]
        final_prompt: str

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
        st.write("### Inputs")
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
            height=100,
        )

        # st.checkbox("Blog Generator Mode", key="enable_blog_mode")
        st.checkbox("Enable Internal Cross-Linking", key="enable_crosslinks")
        st.checkbox("Enable HTML Formatting", key="enable_html")

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
                The maximum number of search URLs to consider as training data
                """,
                key="max_search_urls",
                min_value=1,
                max_value=10,
            )

    def render_output(self):
        output_content = st.session_state.get("output_content")
        if output_content:
            st.write("### Generated Content")
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
            st.empty()

    def render_steps(self):
        col1, col2 = st.columns(2)

        with col1:
            scaleserp_results = st.session_state.get("scaleserp_results")
            if scaleserp_results:
                st.write("**ScaleSERP Results**")
                st.json(scaleserp_results, expanded=False)
            else:
                st.empty()

        with col2:
            search_urls = st.session_state.get("search_urls")
            if search_urls:
                st.write("**Search URLs**")
                st.json(search_urls, expanded=False)
            else:
                st.empty()

        summarized_urls = st.session_state.get("summarized_urls")
        if summarized_urls:
            st.write("**Summarized URLs**")
            st.json(summarized_urls, expanded=False)
        else:
            st.empty()

        final_prompt = st.session_state.get("final_prompt")
        if final_prompt:
            st.text_area(
                "Final Prompt",
                value=final_prompt,
                height=400,
                disabled=True,
            )
        else:
            st.empty()

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
                scrollable_html(output_content[0])
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

        scaleserp_results = call_scaleserp(
            request.search_query,
            include_fields=request.scaleserp_search_field,
        )
        search_urls = _extract_search_urls(request, scaleserp_results)[
            : request.max_search_urls
        ]

        state["scaleserp_results"] = scaleserp_results
        state["search_urls"] = search_urls

        yield from _gen_final_prompt(request, state)

        yield "Generating content using GPT-3..."

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
        partial(
            call_scaleserp,
            include_fields="organic_results",
        ),
        # fmt: off
        [
            f"site:{host} {keyword}"
            for keyword in relevant_keywords
        ],
    )

    for keyword, results in zip(relevant_keywords, all_results):
        try:
            href = results["organic_results"][0]["link"]
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
        api_provider="openai",
        engine="text-davinci-003",
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
        GPT3_MAX_ALLOED_TOKENS - request.max_tokens - calc_gpt_tokens(end_input_prompt)
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
    return BeautifulSoup(text, "html.parser").get_text(separator=" ", strip=True)


@st.cache(show_spinner=False)
def _call_summarize_url(url: str) -> (str, str):
    r = requests.get(
        url,
        headers={"User-Agent": random.choice(FAKE_USER_AGENTS)},
        timeout=EXTERNAL_REQUEST_TIMEOUT_SEC,
    )
    r.raise_for_status()
    doc = readability.Document(r.text)
    return doc.title(), doc.summary()


def _extract_search_urls(
    request: SEOSummaryPage.RequestModel, scaleserp_results: dict
) -> list[str]:
    search_urls = [
        result["link"]
        for result in scaleserp_results[request.scaleserp_search_field]
        if furl(result["link"]).host not in BANNED_HOSTS
    ]
    random.shuffle(search_urls)
    return search_urls


if __name__ == "__main__":
    SEOSummaryPage().render()
