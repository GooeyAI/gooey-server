import typing

from pydantic import BaseModel

import gooey_ui as st
from daras_ai_v2.GoogleGPT import render_output_with_refs
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import document_uploader
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.google_search import call_scaleserp_rq
from daras_ai_v2.language_model import LargeLanguageModels
from daras_ai_v2.language_model_settings_widgets import language_model_settings
from daras_ai_v2.scaleserp_location_picker_widget import scaleserp_location_picker
from daras_ai_v2.vector_search import render_sources_widget
from recipes.DocSearch import DocSearchPage, render_doc_search_step

DEFAULT_GOOGLE_GPT_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/assets/WEBSEARCH%20%2B%20CHATGPT.jpg"


class RelatedDocSearchResponse(DocSearchPage.ResponseModel):
    search_query: str


class RelatedQnADocPage(BasePage):
    title = '"People Also Ask" Answers from a Doc'
    slug_versions = ["related-qna-maker-doc"]

    price = 100

    class RequestModel(BaseModel):
        search_query: str
        documents: list[str] | None
        task_instructions: str | None

        selected_model: typing.Literal[
            tuple(e.name for e in LargeLanguageModels)
        ] | None
        avoid_repetition: bool | None
        num_outputs: int | None
        quality: float | None
        max_tokens: int | None
        max_references: int | None
        max_context_words: int | None
        scroll_jump: int | None

        sampling_temperature: float | None

        scaleserp_search_field: str | None
        scaleserp_locations: list[str] | None

    class ResponseModel(BaseModel):
        output_queries: list[RelatedDocSearchResponse]
        scaleserp_results: dict

    def render_description(self) -> str:
        return "This workflow gets the related queries for your Google search, searches your custom domain and builds answers using the results and GPT."

    def render_form_v2(self):
        st.text_input("##### Search Query", key="search_query")
        document_uploader("##### Documents")

    def validate_form_v2(self):
        assert st.session_state.get(
            "search_query", ""
        ).strip(), "Please enter a search query"
        assert st.session_state.get("documents"), "Please provide at least 1 Document"

    def render_output(self):
        render_qna_outputs(st.session_state, 300)

    def render_example(self, state: dict):
        st.write("**Search Query**")
        st.write("```properties\n" + state.get("search_query", "") + "\n```")
        site_filter = state.get("site_filter")
        if site_filter:
            st.write(f"**Site** \\\n{site_filter}")
        render_qna_outputs(state, 200)

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
        from recipes.RelatedQnA import RelatedQnAPage
        from recipes.CompareLLM import CompareLLMPage

        return [
            RelatedQnAPage,
            SEOSummaryPage,
            DocSearchPage,
            CompareLLMPage,
        ]

    def preview_description(self, state: dict) -> str:
        return 'This workflow finds the related queries (aka "People also ask") for a Google search, searches your doc, pdf or file (from a URL or via an upload) and then generates answers using vector DB results from your docs.'

    def render_steps(self):
        scaleserp_results = st.session_state.get("scaleserp_results")
        if scaleserp_results:
            st.write("**ScaleSERP Results**")
            st.json(scaleserp_results, expanded=False)
        output_queries = st.session_state.get("output_queries", [])
        for i, result in enumerate(output_queries):
            st.write("---")
            st.write(f"##### {i + 1}. _{result.get('search_query')}_")
            render_doc_search_step(
                result.get("final_prompt", ""),
                result.get("output_text", []),
                result.get("references", []),
            )

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: RelatedQnADocPage.RequestModel = self.RequestModel.parse_obj(state)
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
            lambda ques: run_doc_search(state.copy(), ques),
            related_questions,
            max_workers=4,
        )


def run_doc_search(state: dict, related_question: str):
    state["search_query"] = related_question
    for _ in DocSearchPage().run(state):
        pass
    return RelatedDocSearchResponse.parse_obj(state).dict()


def render_qna_outputs(state, height):
    output_queries = state.get("output_queries", [])
    for output in output_queries:
        output_text = output.get("output_text", [])
        if not output_text:
            continue
        references = output.get("references", [])
        st.write(f"**{output.get('search_query')}**")
        render_output_with_refs(
            {"output_text": output_text, "references": references}, height
        )
        render_sources_widget(references)
        st.write("---")
