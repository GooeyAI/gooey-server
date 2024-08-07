import math
import typing

from furl import furl
from pydantic import BaseModel

import gooey_gui as gui
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import (
    bulk_documents_uploader,
    is_user_uploaded_url,
    citation_style_selector,
    doc_search_advanced_settings,
    query_instructions_widget,
    doc_extract_selector,
)
from daras_ai_v2.exceptions import UserError
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
from daras_ai_v2.prompt_vars import render_prompt_vars
from daras_ai_v2.query_generator import generate_final_search_query
from daras_ai_v2.search_ref import (
    SearchReference,
    render_output_with_refs,
    CitationStyles,
    apply_response_formattings_prefix,
    apply_response_formattings_suffix,
)
from daras_ai_v2.vector_search import (
    DocSearchRequest,
    get_top_k_references,
    references_as_prompt,
    render_sources_widget,
)

DEFAULT_DOC_SEARCH_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/bcc7aa58-93fe-11ee-a083-02420a0001c8/Search%20your%20docs.jpg.png"


class DocSearchPage(BasePage):
    PROFIT_CREDITS = 3

    title = "Search your Docs with GPT"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/cbbb4dc6-88d7-11ee-bf6c-02420a000166/Search%20your%20docs%20with%20gpt.png.png"
    workflow = Workflow.DOC_SEARCH
    slug_versions = ["doc-search"]

    sane_defaults = {
        "sampling_temperature": 0.1,
        "max_tokens": 256,
        "num_outputs": 1,
        "quality": 1.0,
        "max_references": 3,
        "max_context_words": 200,
        "scroll_jump": 5,
        "avoid_repetition": True,
        "selected_model": LargeLanguageModels.text_davinci_003.name,
        "citation_style": CitationStyles.number.name,
        "dense_weight": 1.0,
    }

    class RequestModelBase(DocSearchRequest, BasePage.RequestModel):
        task_instructions: str | None
        query_instructions: str | None

        selected_model: (
            typing.Literal[tuple(e.name for e in LargeLanguageModels)] | None
        )

        citation_style: typing.Literal[tuple(e.name for e in CitationStyles)] | None

    class RequestModel(LanguageModelSettings, RequestModelBase):
        pass

    class ResponseModel(BaseModel):
        output_text: list[str]

        references: list[SearchReference]
        final_prompt: str
        final_search_query: str | None

    @classmethod
    def get_example_preferred_fields(self, state: dict) -> list[str]:
        return ["documents"]

    def render_form_v2(self):
        gui.text_area("#### Search Query", key="search_query")
        bulk_documents_uploader("#### Documents")

    def validate_form_v2(self):
        search_query = gui.session_state.get("search_query", "").strip()
        assert search_query, "Please enter a Search Query"
        assert gui.session_state.get("documents"), "Please provide at least 1 Document"

    def related_workflows(self) -> list:
        from recipes.EmailFaceInpainting import EmailFaceInpaintingPage
        from recipes.SEOSummary import SEOSummaryPage
        from recipes.VideoBots import VideoBotsPage
        from recipes.GoogleGPT import GoogleGPTPage

        return [
            GoogleGPTPage,
            EmailFaceInpaintingPage,
            SEOSummaryPage,
            VideoBotsPage,
        ]

    def render_output(self):
        render_output_with_refs(gui.session_state)
        refs = gui.session_state.get("references", [])
        render_sources_widget(refs)

    def render_example(self, state: dict):
        render_documents(state)
        gui.html("**Search Query**")
        gui.write("```properties\n" + state.get("search_query", "") + "\n```")
        render_output_with_refs(state, 200)

    def render_settings(self):
        gui.text_area(
            "##### 👩‍🏫 Task Instructions",
            key="task_instructions",
            height=300,
        )
        gui.write("---")
        selected_model = language_model_selector()
        language_model_settings(selected_model)
        gui.write("---")
        gui.write("##### 🔎 Document Search Settings")
        citation_style_selector()
        doc_extract_selector(self.request and self.request.user)
        query_instructions_widget()
        gui.write("---")
        doc_search_advanced_settings()

    def preview_image(self, state: dict) -> str | None:
        return DEFAULT_DOC_SEARCH_META_IMG

    def preview_description(self, state: dict) -> str:
        return "Add your PDF, Word, HTML or Text docs, train our AI on them with OpenAI embeddings & vector search and then process results with a GPT3 script. This workflow is perfect for anything NOT in ChatGPT: 250-page compliance PDFs, training manuals, your diary, etc."

    def render_steps(self):
        render_doc_search_step(gui.session_state)

    def render_usage_guide(self):
        youtube_video("Xe4L_dQ2KvU")

    def run_v2(
        self,
        request: "DocSearchPage.RequestModel",
        response: "DocSearchPage.ResponseModel",
    ):
        model = LargeLanguageModels[request.selected_model]

        query_instructions = (request.query_instructions or "").strip()
        if query_instructions:
            response.final_search_query = generate_final_search_query(
                request=request, instructions=query_instructions
            )
        else:
            response.final_search_query = request.search_query

        response.references = yield from get_top_k_references(
            DocSearchRequest.parse_obj(
                {
                    **request.dict(),
                    "search_query": response.final_search_query,
                },
            ),
            current_user=self.request and self.request.user,
        )

        # empty search result, abort!
        if not response.references:
            raise EmptySearchResults(request.search_query)

        response.final_prompt = ""
        # add search results to the prompt
        response.final_prompt += references_as_prompt(response.references) + "\n\n"
        # add task instructions
        task_instructions = (request.task_instructions or "").strip()
        if not task_instructions:
            response.output_text = []
            return
        task_instructions = render_prompt_vars(
            prompt=task_instructions, state=request.dict() | response.dict()
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

        citation_style = (
            request.citation_style and CitationStyles[request.citation_style]
        ) or None
        all_refs_list = apply_response_formattings_prefix(
            response.output_text, response.references, citation_style
        )
        apply_response_formattings_suffix(
            all_refs_list, response.output_text, citation_style
        )

    def get_raw_price(self, state: dict) -> float:
        return self.get_total_linked_usage_cost_in_credits() + self.PROFIT_CREDITS

    def additional_notes(self):
        try:
            model = LargeLanguageModels[gui.session_state["selected_model"]].value
        except KeyError:
            model = "LLM"
        return f"\n*Breakdown: {math.ceil(self.get_total_linked_usage_cost_in_credits())} ({model}) + {self.PROFIT_CREDITS}/run*"


def render_documents(state, label="**Documents**", *, key="documents"):
    documents = state.get(key, [])
    if not documents:
        return
    gui.write(label)
    for doc in documents:
        if is_user_uploaded_url(doc):
            f = furl(doc)
            filename = f.path.segments[-1]
        else:
            filename = doc
        gui.write(f"🔗[*{filename}*]({doc})")


def render_doc_search_step(state: dict):
    final_search_query = state.get("final_search_query")
    if final_search_query:
        gui.text_area("**Final Search Query**", value=final_search_query, disabled=True)

    references = state.get("references")
    if references:
        gui.write("**References**")
        gui.json(references, expanded=False)

    final_prompt = state.get("final_prompt")
    if final_prompt:
        gui.text_area(
            "**Final Prompt**",
            value=final_prompt,
            height=400,
            disabled=True,
        )

    output_text = state.get("output_text", [])
    for idx, text in enumerate(output_text):
        gui.text_area(
            f"**Output Text**",
            help=f"output {idx}",
            disabled=True,
            value=text,
        )


class EmptySearchResults(UserError):
    def __init__(self, search_query: str):
        self.search_query = search_query
        super().__init__(f"Your search “{search_query}” did not match any documents.")
