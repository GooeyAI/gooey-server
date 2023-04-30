import typing
from enum import Enum

import streamlit as st
from llama_index.langchain_helpers.text_splitter import SentenceSplitter
from pydantic import BaseModel
from streamlit.runtime.uploaded_file_manager import UploadedFile

from daras_ai.image_input import upload_st_file
from daras_ai_v2.GoogleGPT import render_outputs, GoogleGPTPage
from daras_ai_v2.asr import AsrModels
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import (
    document_uploader,
)
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.language_model import (
    LargeLanguageModels,
    run_language_model,
    model_max_tokens,
    calc_gpt_tokens,
)
from daras_ai_v2.language_model_settings_widgets import language_model_settings
from recipes.DocSearch import (
    doc_url_to_text_pages,
    doc_url_to_metadata,
    DocSearchPage,
)

DEFAULT_DOC_SEARCH_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/assets/DOC%20SEARCH.gif"


class CombineDocumentsChains(Enum):
    map_reduce = "Map Reduce"
    # refine = "Refine"
    # stuff = "Stuffing (Only works for small documents)"


class PromptTreeNode(BaseModel):
    prompt: str
    children: list["PromptTreeNode"]


PromptTree = list[PromptTreeNode]


class DocSummaryPage(BasePage):
    title = "Summarize your Docs with GPT"
    slug_versions = ["doc-summary"]

    price = 225

    sane_defaults = {
        "sampling_temperature": 0.1,
        "max_tokens": 256,
        "num_outputs": 1,
        "quality": 1.0,
        "avoid_repetition": True,
        "selected_model": LargeLanguageModels.text_davinci_003.name,
    }

    class RequestModel(BaseModel):
        documents: list[str]

        task_instructions: str | None
        merge_instructions: str | None

        selected_model: typing.Literal[
            tuple(e.name for e in LargeLanguageModels)
        ] | None
        avoid_repetition: bool | None
        num_outputs: int | None
        quality: float | None
        max_tokens: int | None
        sampling_temperature: float | None

        chain_type: typing.Literal[tuple(e.name for e in CombineDocumentsChains)] | None

        selected_asr_model: typing.Literal[tuple(e.name for e in AsrModels)] | None
        google_translate_target: str | None

    class ResponseModel(BaseModel):
        output_text: list[str]

        prompt_tree: PromptTree | None
        final_prompt: str

    def render_form_v2(self):
        document_uploader("##### 📎 Documents")
        st.text_area("##### 👩‍💻 Instructions", key="task_instructions", height=150)

    def render_settings(self):
        st.text_area(
            """
##### 📄+📄 Merge Instructions
Prompt for merging several outputs together 
        """,
            key="merge_instructions",
            height=150,
        )

        #         enum_selector(
        #             CombineDocumentsChains,
        #             label="""
        # """,
        #             key="chain_type",
        #         )
        st.write("---")

        language_model_settings()

    def validate_form_v2(self):
        search_query = st.session_state.get("task_instructions", "").strip()
        assert search_query, "Please enter the Instructions"

        document_files: list[UploadedFile] | None = st.session_state.get(
            "__documents_files"
        )
        if document_files:
            uploaded = []
            for f in document_files:
                if f.name == "urls.txt":
                    uploaded.extend(f.getvalue().decode().splitlines())
                else:
                    uploaded.append(upload_st_file(f))
            st.session_state["documents"] = uploaded
        assert st.session_state.get("documents"), "Please provide at least 1 Document"

    def render_output(self):
        render_outputs(st.session_state, 300)

    def render_example(self, state: dict):
        st.write("**Instructions**")
        st.write("```properties\n" + state.get("task_instructions", "") + "\n```")
        render_outputs(state, 200)

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

    def related_workflows(self) -> list:
        from recipes.VideoBots import VideoBotsPage
        from recipes.SEOSummary import SEOSummaryPage

        return [GoogleGPTPage, DocSearchPage, VideoBotsPage, SEOSummaryPage]

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: DocSummaryPage.RequestModel = self.RequestModel.parse_obj(state)

        yield "Downloading documents..."

        full_text = ""
        for f_url in request.documents:
            doc_meta = doc_url_to_metadata(f_url)
            pages = doc_url_to_text_pages(
                f_url=f_url,
                doc_meta=doc_meta,
                selected_asr_model=request.selected_asr_model,
                google_translate_target=request.google_translate_target,
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
    max_tokens_bound = model_max_tokens[model] // 3 - prompt_token_count
    assert request.max_tokens <= max_tokens_bound, (
        f"To summarize accurately, output size must be at max {max_tokens_bound} for {model.value}, "
        f"but got {request.max_tokens}. Please reduce the output size."
    )

    # logic: model max tokens = prompt + output + document chunk
    chunk_size = model_max_tokens[model] - (prompt_token_count + request.max_tokens)
    text_splitter = SentenceSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_size // 10,
    )
    texts = text_splitter.split_text(full_text)

    def llm(p: str) -> str:
        return run_language_model(
            prompt=p,
            model=request.selected_model,
            max_tokens=request.max_tokens,
            quality=request.quality,
            num_outputs=request.num_outputs,
            temperature=request.sampling_temperature,
            avoid_repetition=request.avoid_repetition,
        )[0]

    state["prompt_tree"] = prompt_tree = []
    llm_prompts = []
    for chunk in texts:
        prompt = MAP_REDUCE_PROMPT.format(
            documents=documents_as_prompt([chunk]),
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
