import typing
from enum import Enum

from daras_ai_v2.pydantic_validation import FieldHttpUrl
from pydantic import BaseModel, Field

import gooey_ui as st
from bots.models import Workflow
from daras_ai_v2.asr import AsrModels
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import (
    bulk_documents_uploader,
)
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.language_model import (
    LargeLanguageModels,
    run_language_model,
    calc_gpt_tokens,
    ResponseFormatType,
)
from daras_ai_v2.language_model_settings_widgets import (
    language_model_settings,
    language_model_selector,
    LanguageModelSettings,
)
from daras_ai_v2.pt import PromptTree
from daras_ai_v2.text_splitter import text_splitter
from daras_ai_v2.vector_search import (
    doc_url_to_text_pages,
    doc_url_to_file_metadata,
)
from recipes.DocSearch import (
    DocSearchPage,
    render_documents,
)
from recipes.GoogleGPT import render_output_with_refs, GoogleGPTPage

DEFAULT_DOC_SUMMARY_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/f35796d2-93fe-11ee-b86c-02420a0001c7/Summarize%20with%20GPT.jpg.png"


class CombineDocumentsChains(Enum):
    map_reduce = "Map Reduce"
    # refine = "Refine"
    # stuff = "Stuffing (Only works for small documents)"


class DocSummaryPage(BasePage):
    title = "Summarize your Docs with GPT"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/1f858a7a-88d8-11ee-a658-02420a000163/Summarize%20your%20docs%20with%20gpt.png.png"
    workflow = Workflow.DOC_SUMMARY
    slug_versions = ["doc-summary"]

    price = 225

    sane_defaults = {
        "sampling_temperature": 0.1,
        "max_tokens": 256,
        "num_outputs": 1,
        "quality": 1.0,
        "avoid_repetition": True,
        "selected_model": LargeLanguageModels.text_davinci_003.name,
        "chain_type": CombineDocumentsChains.map_reduce.name,
    }

    class RequestModelBase(BasePage.RequestModel):
        documents: list[FieldHttpUrl]

        task_instructions: str | None
        merge_instructions: str | None

        selected_model: (
            typing.Literal[tuple(e.name for e in LargeLanguageModels)] | None
        )

        chain_type: typing.Literal[tuple(e.name for e in CombineDocumentsChains)] | None

        selected_asr_model: typing.Literal[tuple(e.name for e in AsrModels)] | None
        google_translate_target: str | None

    class RequestModel(LanguageModelSettings, RequestModelBase):
        pass

    class ResponseModel(BaseModel):
        output_text: list[str]

        prompt_tree: PromptTree | None
        final_prompt: str

    @classmethod
    def get_example_preferred_fields(cls, state: dict) -> list[str]:
        return ["task_instructions", "merge_instructions"]

    def preview_image(self, state: dict) -> str | None:
        return DEFAULT_DOC_SUMMARY_META_IMG

    def render_form_v2(self):
        bulk_documents_uploader("#### 📎 Documents")
        st.text_area("#### 👩‍💻 Instructions", key="task_instructions")

    def render_settings(self):
        st.text_area(
            """
##### 📄+📄 Merge Instructions
Prompt for merging several outputs together 
        """,
            key="merge_instructions",
        )

        #         enum_selector(
        #             CombineDocumentsChains,
        #             label="""
        # """,
        #             key="chain_type",
        #         )
        st.write("---")

        selected_model = language_model_selector()
        language_model_settings(selected_model)

    def preview_description(self, state: dict) -> str:
        return "Upload any collection of PDFs, docs and/or audio files and we'll transcribe them. Then give any GPT based instruction and we'll do a map-reduce and return the result. Great for summarizing large data sets to create structured data. Check out the examples for more."

    def validate_form_v2(self):
        search_query = st.session_state.get("task_instructions", "").strip()
        assert search_query, "Please enter the Instructions"
        assert st.session_state.get("documents"), "Please provide at least 1 Document"

    def render_output(self):
        render_output_with_refs(st.session_state)

    def render_example(self, state: dict):
        render_documents(state)
        st.write("**Instructions**")
        st.write("```properties\n" + state.get("task_instructions", "") + "\n```")
        render_output_with_refs(state, 200)

    def render_steps(self):
        prompt_tree = st.session_state.get("prompt_tree", {})
        if prompt_tree:
            st.write("**Prompt Tree**")
            st.json(prompt_tree, expanded=False)

        final_prompt = st.session_state.get("final_prompt")
        if final_prompt:
            st.text_area(
                "**Final Prompt**",
                value=final_prompt,
                disabled=True,
            )
        else:
            st.div()

        output_text: list = st.session_state.get("output_text", [])
        for idx, text in enumerate(output_text):
            st.text_area(
                f"**Output Text**",
                help=f"output {idx}",
                disabled=True,
                value=text,
            )

    def related_workflows(self) -> list:
        from recipes.VideoBots import VideoBotsPage
        from recipes.SEOSummary import SEOSummaryPage

        return [GoogleGPTPage, DocSearchPage, VideoBotsPage, SEOSummaryPage]

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: DocSummaryPage.RequestModel = self.RequestModel.parse_obj(state)

        yield "Downloading documents..."

        full_text = ""
        for f_url in request.documents:
            pages = doc_url_to_text_pages(
                f_url=f_url,
                file_meta=doc_url_to_file_metadata(f_url),
                selected_asr_model=request.selected_asr_model,
            )
            full_text += "\n\n".join(pages)

        chain_type = CombineDocumentsChains[request.chain_type]
        match chain_type:
            case CombineDocumentsChains.map_reduce:
                state["output_text"] = yield from _map_reduce(request, full_text, state)
                state["final_prompt"] = state["prompt_tree"][-1]["prompt"]
            case _:
                raise NotImplementedError(f"{chain_type} not implemented")


MAP_REDUCE_PROMPT = """
{documents}
**********
[Instructions]
{instructions}
**********
Read the Documents above and produce a Response that best follows the given Instructions.
""".strip()


def documents_as_prompt(docs: list[str], sep="\n\n") -> str:
    return sep.join(
        f'''
[Document {idx + 1}]: """
{text}
"""
'''.strip()
        for idx, text in enumerate(docs)
    )


def _map_reduce(request: "DocSummaryPage.RequestModel", full_text: str, state: dict):
    model = LargeLanguageModels[request.selected_model]

    task_instructions = request.task_instructions.strip()
    merge_instructions = request.merge_instructions.strip()

    safety_buffer = 100
    prompt_token_count = (
        calc_gpt_tokens(task_instructions + merge_instructions) + safety_buffer
    )

    # to merge 2 outputs, we need to have at least 1/3 of the max tokens available
    max_tokens_bound = (model.context_window - prompt_token_count) // 3
    assert request.max_tokens <= max_tokens_bound, (
        f"To summarize accurately, output size must be at max {max_tokens_bound} for {model.value}, "
        f"but got {request.max_tokens}. Please reduce the output size."
    )

    # logic: model context window = prompt + output + document chunk
    chunk_size = model.context_window - (prompt_token_count + request.max_tokens)
    docs = text_splitter(
        full_text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_size // 10,
    )

    def llm(p: str) -> str:
        return run_language_model(
            prompt=p,
            model=request.selected_model,
            max_tokens=request.max_tokens,
            quality=request.quality,
            num_outputs=request.num_outputs,
            temperature=request.sampling_temperature,
            avoid_repetition=request.avoid_repetition,
            response_format_type=request.response_format_type,
        )[0]

    state["prompt_tree"] = prompt_tree = []
    llm_prompts = []
    for doc in docs:
        prompt = MAP_REDUCE_PROMPT.format(
            documents=documents_as_prompt([doc.text]),
            instructions=task_instructions,
        )
        llm_prompts.append(prompt)
        prompt_tree.append({"prompt": prompt, "children": []})

    progress = 0
    extra_doc = None

    while True:
        progress += 1
        yield f"[{progress}] Summarizing using {model.value}..."
        documents = map_parallel(llm, llm_prompts, max_workers=4)
        # append the left over document from the previous iteration
        if extra_doc:
            documents.append(extra_doc)
        # reached the end
        if len(documents) < 2:
            break
        # build the prompts for the next batch
        llm_prompts = []
        prompt_tree_next = []
        extra_doc = None
        # combine previous documents with a batch size of 2
        batch_size = 2
        for idx in range(0, len(documents), batch_size):
            two_docs = documents[idx : idx + batch_size]
            if len(two_docs) <= 1:
                # use this left over document in the next iteration
                extra_doc = two_docs[0]
            else:
                prompt = MAP_REDUCE_PROMPT.format(
                    documents=documents_as_prompt(two_docs),
                    instructions=merge_instructions,
                )
                llm_prompts.append(prompt)
                prompt_tree_next.append(
                    {"prompt": prompt, "children": prompt_tree[idx : idx + 2]}
                )
        # use the updated prompt tree in the next iteration
        state["prompt_tree"] = prompt_tree = prompt_tree_next

    return documents
