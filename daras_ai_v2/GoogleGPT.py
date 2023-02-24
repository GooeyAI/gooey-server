import datetime
import re
import typing

import streamlit as st
from furl import furl
from pydantic import BaseModel

from daras_ai_v2.base import BasePage
from daras_ai_v2.google_search import call_scaleserp
from daras_ai_v2.language_model import run_language_model
from daras_ai_v2.language_model_settings_widgets import language_model_settings


class SearchReference(typing.TypedDict):
    url: str
    title: str
    snippet: str
    score: float


class GoogleGPTPage(BasePage):
    title = "Google GPT"
    slug_versions = ["google-gpt"]

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
        site_filter: str
        # selected_model: typing.Literal[
        #     tuple(e.name for e in LargeLanguageModels)
        # ] | None

        task_instructions: str | None

        avoid_repetition: bool | None
        num_outputs: int | None
        quality: float | None
        max_tokens: int | None
        sampling_temperature: float | None

        max_search_urls: int | None

    class ResponseModel(BaseModel):
        output_text: list[str]

        scaleserp_results: dict
        # search_urls: list[str]
        # summarized_urls: list[dict]
        references: list[SearchReference]
        final_prompt: str

    def render_form_v2(self):
        st.text_input("##### Google Search Query", key="search_query")
        st.text_input("Search on a specific site *(optional)*", key="site_filter")

    def validate_form_v2(self):
        assert st.session_state.get(
            "search_query", ""
        ).strip(), "Please enter a search query"

    def render_output(self):
        render_outputs(st.session_state, 300)

        with st.expander("Sources"):
            for idx, ref in enumerate(st.session_state.get("references", [])):
                st.write(
                    f"{idx + 1}. [{ref['title']}]({ref['url']}) \\\n*{ref['snippet']}*"
                )

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

        st.number_input(
            label="""
            ###### Max References
            The maximum number of search URLs to consider as References
            """,
            key="max_search_urls",
            min_value=1,
            max_value=10,
        )

    def render_steps(self):
        col1, col2 = st.columns(2)

        with col1:
            scaleserp_results = st.session_state.get("scaleserp_results")
            if scaleserp_results:
                st.write("**ScaleSERP Results**")
                st.json(scaleserp_results, expanded=False)
            else:
                st.empty()

        # with col2:
        #     search_urls = st.session_state.get("search_urls")
        #     if search_urls:
        #         st.write("**Search URLs**")
        #         st.json(search_urls, expanded=False)
        #     else:
        #         st.empty()

        # summarized_urls = st.session_state.get("summarized_urls")
        # if summarized_urls:
        #     st.write("**Summarized URLs**")
        #     st.json(summarized_urls, expanded=False)
        # else:
        #     st.empty()

        final_prompt = st.session_state.get("final_prompt")
        if final_prompt:
            st.text_area(
                "**Final Prompt**",
                value=final_prompt,
                height=400,
                disabled=True,
            )
        else:
            st.empty()

        output_text: list = st.session_state.get("output_text", [])
        for idx, text in enumerate(output_text):
            st.text_area(
                f"**Output Text**",
                help=f"output {idx}",
                disabled=True,
                value=text,
                height=200,
            )

        st.write("**References**")
        st.json(st.session_state.get("references", []), expanded=False)

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: GoogleGPTPage.RequestModel = self.RequestModel.parse_obj(state)

        yield "Googling..."

        search_query = request.search_query

        if request.site_filter:
            f = furl(request.site_filter)
            search_query = f"site:{f.host}{f.path} {search_query}"

        scaleserp_search_field = "organic_results"
        state["scaleserp_results"] = scaleserp_results = call_scaleserp(
            search_query,
            include_fields=scaleserp_search_field,
        )

        state["references"] = references = []

        utcnow = datetime.datetime.utcnow().strftime("%B %d, %Y %H:%M:%S %Z")
        task_instructions = request.task_instructions.replace(
            "{{ datetime.utcnow }}", utcnow
        )
        prompt = task_instructions.strip() + "\n\n"
        prompt += "Search Results:\n"
        ref_num = 1
        for item in scaleserp_results.get(scaleserp_search_field, []):
            try:
                url = item["link"]
                title = item["title"]
                snippet = item["snippet"]
            except KeyError:
                continue
            prompt += f"[{ref_num}] {snippet}\n"
            references.append(
                {"url": url, "title": title, "snippet": snippet, "score": 1.0}
            )
            if ref_num >= request.max_search_urls:
                break
            ref_num += 1
        if not references:
            raise ValueError(
                f"Your search - {request.search_query} - did not match any documents."
            )
        prompt += f"Question: {request.search_query}\nAnswer:"
        state["final_prompt"] = prompt

        yield "Generating answer using GPT-3..."
        output_text = run_language_model(
            api_provider="openai",
            engine="text-davinci-003",
            quality=request.quality,
            num_outputs=request.num_outputs,
            temperature=request.sampling_temperature,
            prompt=prompt,
            max_tokens=request.max_tokens,
            stop=None,
            avoid_repetition=request.avoid_repetition,
        )
        state["output_text"] = output_text


def render_outputs(state, height):
    output_text = state.get("output_text", [])
    if output_text:
        st.write("**Answer**")
    for text in output_text:
        html = render_text_with_refs(text, state.get("references", []))
        st.write(
            # language=html
            f"""<div style="max-height: {height}px;" class="gooey-output-text"><p>{html}</p></div>""",
            unsafe_allow_html=True,
        )


def render_text_with_refs(text: str, references: list[SearchReference]):
    html = ""
    last_match_end = 0
    for match in re.finditer(r"(\[[\d,\s]+\]([\,\.\s]*))+", text):
        end_separator = match.group(2)
        ref_str = text[match.start() : match.end()].strip()
        ref_numbers = set(int(num) for num in re.findall(r"\d+", ref_str))
        html += text[last_match_end : match.start()].strip()
        ref_links = []
        for ref_num in ref_numbers:
            try:
                url = references[ref_num - 1]["url"]
            except IndexError:
                continue
            ref_links.append(f'<a href="{url}">{ref_num}</a>')
        ref_str_clean = ", ".join(ref_links)
        if ref_links:
            html += f"<sup>[{ref_str_clean}]</sup>"
        html += end_separator
        last_match_end = match.end()
    html += text[last_match_end:]
    return html
