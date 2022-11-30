import random
import typing

import readability
import requests
import streamlit as st
from furl import furl
from html2text import html2text
from pydantic import BaseModel

from daras_ai_v2 import settings
from daras_ai_v2.base import BasePage
from daras_ai_v2.fake_user_agents import FAKE_USER_AGENTS
from daras_ai_v2.language_model import (
    run_language_model,
    GPT3_MAX_ALLOED_TOKENS,
    calc_gpt_tokens,
)
from daras_ai_v2.settings import EXTERNAL_REQUEST_TIMEOUT_SEC

STOP_SEQ = "###"


class SEOSummaryPage(BasePage):
    title = "Create the best SEO content from any query"
    slug = "SEOSummary"

    sane_defaults = dict(
        search_query="rugs",
        keywords="outdoor rugs,8x10 rugs,rug sizes,checkered rugs,5x7 rugs",
        title="Ruggable",
        company_url="https://ruggable.com",
        scaleserp_search_field="organic_results",
        do_html2text=True,
        sampling_temperature=0.8,
        max_tokens=1024,
        num_outputs=1,
        quality=1.0,
        max_search_urls=10,
        task_instructions="I will give you a URL and focus keywords and using the high ranking content from the google search results below you will write 500 words for the given url.",
    )

    class RequestModel(BaseModel):
        search_query: str
        keywords: str
        title: str
        company_url: str

        task_instructions: str | None

        scaleserp_search_field: str | None
        do_html2text: bool | None

        sampling_temperature: float | None
        max_tokens: int | None
        num_outputs: int | None
        quality: float | None

        max_search_urls: int | None

    class ResponseModel(BaseModel):
        output_content: list[str]

        scaleserp_results: dict
        search_urls: list[str]
        summarized_urls: list[dict]
        final_prompt: str

    def render_form_v2(self):
        st.write("### Inputs")
        st.text_input("Search Query", key="search_query")
        st.text_area("Keywords", key="keywords")
        st.text_input("Title", key="title")
        st.text_input("Company URL", key="company_url")

    def validate_form_v2(self):
        assert st.session_state["search_query"], "Please provide Search Query"
        assert st.session_state["keywords"], "Please provide Keywords"
        assert st.session_state["title"], "Please provide Title"
        assert st.session_state["company_url"], "Please provide Company URL"

    def render_settings(self):
        st.text_area(
            "Task Instructions",
            key="task_instructions",
            height=200,
        )

        st.write("---")

        st.write(
            "ScaleSERP [Search Property](https://www.scaleserp.com/docs/search-api/results/google/search)"
        )
        st.text_input(
            "scaleserp_search_field",
            label_visibility="collapsed",
            key="scaleserp_search_field",
        )
        st.write("---")

        st.checkbox("Convert HTML->Text?", key="do_html2text")

        st.write("---")

        col1, col2 = st.columns(2)
        with col1:
            st.slider(
                label="Number of Outputs",
                key="num_outputs",
                min_value=1,
                max_value=4,
            )
        with col2:
            st.slider(
                label="Quality",
                key="quality",
                min_value=1.0,
                max_value=5.0,
                step=0.1,
            )

        st.write(
            """
            ###### Model Risk Factor 
            *(Sampling Temperature)*
            
            Higher values allow the model to take more risks.
            Try 0.9 for more creative applications, 
            and 0 for ones with a well-defined answer. 
            """
        )
        col1, _ = st.columns(2)
        with col1:
            st.slider(
                label="model risk",
                label_visibility="collapsed",
                key="sampling_temperature",
                min_value=0.0,
                max_value=1.0,
            )

        st.write("---")

        col1, col2 = st.columns(2)

        with col1:
            st.write(
                """
                ###### Max Search URLs
                The maximum number of search URLs to consider as training data
                """
            )
            st.number_input(
                label="max_search_urls",
                label_visibility="collapsed",
                key="max_search_urls",
                min_value=1,
                max_value=10,
            )

        with col2:
            st.write(
                """
                ###### Max Output Tokens
                The maximum number of [tokens](https://beta.openai.com/tokenizer) to generate in the completion.
                """
            )
            st.number_input(
                label="max_tokens",
                label_visibility="collapsed",
                key="max_tokens",
                min_value=1,
                max_value=4096,
            )

    def render_output(self):
        output_content = st.session_state.get("output_content")
        if output_content:
            st.write("### Generated Content")
            for text in output_content:
                st.text_area(
                    "Output",
                    label_visibility="collapsed",
                    value=text,
                    height=200,
                    disabled=True,
                )
        else:
            st.empty()

        with st.expander("Steps"):
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
            Keywords `{state.get('keywords', '')}` \\
            Title `{state.get('title', '')}` \\
            Company URL `{state.get('company_url', '')}`               
            """
        )

        output_content = state.get("output_content")
        if output_content:
            st.text_area(
                "Generated Content",
                value=output_content[0],
                height=200,
                disabled=True,
            )

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: SEOSummaryPage.RequestModel = self.RequestModel.parse_obj(state)

        yield "Running ScaleSERP..."

        scaleserp_results = _call_scaleserp(
            request.search_query, request.scaleserp_search_field
        )
        search_urls = _extract_search_urls(request, scaleserp_results)[
            : request.max_search_urls
        ]

        state["scaleserp_results"] = scaleserp_results
        state["search_urls"] = search_urls

        yield from _gen_final_prompt(request, state)

        yield "Running GPT-3..."

        state["output_content"] = _run_lm(request, state["final_prompt"])


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
            "URL: " + request.company_url,
            "Keywords: " + request.keywords,
            "Content: " + padded_stop_seq,
        ]
    )

    max_allowed_tokens = (
        GPT3_MAX_ALLOED_TOKENS - request.max_tokens - calc_gpt_tokens(end_input_prompt)
    )

    state["final_prompt"] = request.task_instructions.strip() + "\n\n"

    for idx, url in enumerate(state["search_urls"]):
        yield f"Summarizing {url}..."

        summary_dict = _summarize_url(request, url)
        if not summary_dict:
            continue

        summarized_urls.append(summary_dict)

        clean_summary = summary_dict["summary"].replace(STOP_SEQ, "")
        padded_summary = padded_stop_seq + clean_summary + padded_stop_seq

        next_prompt_part = "\n".join(
            [
                "Rank: " + str(idx + 1),
                "URL: " + summary_dict["url"],
                "Title: " + summary_dict["title"],
                "Content: " + padded_summary,
            ]
        )

        # used too many tokens, abort!
        if (
            calc_gpt_tokens(state["final_prompt"] + next_prompt_part)
            > max_allowed_tokens
        ):
            continue

        state["final_prompt"] += next_prompt_part
        yield

    # add inputs
    state["final_prompt"] += end_input_prompt
    yield


def _summarize_url(request: SEOSummaryPage.RequestModel, url: str):
    try:
        title, summary = _call_summarize_url(url)
    except requests.RequestException:
        return None

    if request.do_html2text:
        title = html2text(title)
        summary = html2text(summary)
    title = title.strip()
    summary = summary.strip()

    if not summary:
        return None

    return {
        "url": url,
        "title": title,
        "summary": summary,
    }


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
        result["link"] for result in scaleserp_results[request.scaleserp_search_field]
    ]
    random.shuffle(search_urls)
    return search_urls


@st.cache(show_spinner=False)
def _call_scaleserp(search_query: str, search_field: str) -> dict:
    scaleserp_url = furl(
        "https://api.scaleserp.com/search",
        query_params={
            "api_key": settings.SCALESERP_API_KEY,
            "q": search_query,
            "location": "United States",
            "hl": "en",
            "google_domain": "google.com",
            "gl": "us",
            "include_fields": search_field,
        },
    ).url
    r = requests.get(scaleserp_url)
    r.raise_for_status()
    scaleserp_results = r.json()
    return scaleserp_results


if __name__ == "__main__":
    SEOSummaryPage().render()
