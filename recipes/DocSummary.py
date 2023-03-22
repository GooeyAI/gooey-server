import typing
from enum import Enum

import streamlit as st
from langchain import OpenAI
from langchain.chains.summarize import load_summarize_chain
from langchain.chat_models import ChatOpenAI
from langchain.docstore.document import Document
from langchain.prompts import PromptTemplate
from langchain.text_splitter import (
    RecursiveCharacterTextSplitter,
)
from pydantic import BaseModel
from streamlit.runtime.uploaded_file_manager import UploadedFile

from daras_ai.image_input import upload_st_file
from daras_ai_v2 import settings
from daras_ai_v2.GoogleGPT import SearchReference, render_outputs
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import (
    doc_search_settings,
    document_uploader,
)
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.language_model import (
    LargeLanguageModels,
    is_chat_model,
    engine_names,
    GPT3_MAX_ALLOED_TOKENS,
)
from daras_ai_v2.language_model_settings_widgets import language_model_settings
from recipes.DocSearch import doc_url_to_text_pages, doc_url_to_metadata

DEFAULT_DOC_SEARCH_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/assets/DOC%20SEARCH.gif"


class CombineDocumentsChains(Enum):
    map_reduce = "Map Reduce"
    refine = "Refine"
    stuff = "Stuffing (Only works for small documents)"


class DocSummaryPage(BasePage):
    title = "Summarize your Docs with GPT"
    slug_versions = ["doc-summary"]

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
    }

    class RequestModel(BaseModel):
        task_instructions: str | None
        documents: list[str] | None

        selected_model: typing.Literal[
            tuple(e.name for e in LargeLanguageModels)
        ] | None
        avoid_repetition: bool | None
        num_outputs: int | None
        quality: float | None
        max_tokens: int | None
        sampling_temperature: float | None

        chain_type: typing.Literal[tuple(e.name for e in CombineDocumentsChains)] | None

    class ResponseModel(BaseModel):
        output_text: list[str]

        references: list[SearchReference]
        final_prompt: str

    def render_form_v2(self):
        document_uploader("##### Documents")
        st.text_area("##### Instructions", key="task_instructions", height=150)

    def render_settings(self):
        enum_selector(
            CombineDocumentsChains,
            label="""
#### 🦜🔗 LangChain Type
[Read More](https://langchain.readthedocs.io/en/latest/modules/indexes/combine_docs.html)
""",
            key="chain_type",
        )
        st.write("---")

        language_model_settings()
        st.write("---")

        doc_search_settings()

    def validate_form_v2(self):
        search_query = st.session_state.get("task_instructions", "").strip()
        assert search_query, "Please enter the Instructions"

        document_files: list[UploadedFile] | None = st.session_state.get(
            "__document_files"
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
        request: DocSummaryPage.RequestModel = self.RequestModel.parse_obj(state)

        yield "Downloading documents..."

        full_text = ""
        for f_url in request.documents:
            f_name, f_etag = doc_url_to_metadata(f_url)
            pages = doc_url_to_text_pages(f_url, f_name, f_etag)
            full_text += "\n\n".join(pages)

        model = LargeLanguageModels[request.selected_model]

        if is_chat_model(model):
            llm = ChatOpenAI(
                openai_api_key=settings.OPENAI_API_KEY,
                model_name=engine_names[model],
                max_tokens=request.max_tokens,
                n=request.num_outputs,
                temperature=request.sampling_temperature,
                frequency_penalty=0.1 if request.avoid_repetition else 0,
                presence_penalty=0.25 if request.avoid_repetition else 0,
            )
        else:
            llm = OpenAI(
                openai_api_key=settings.OPENAI_API_KEY,
                model_name=engine_names[model],
                max_tokens=request.max_tokens,
                best_of=int(request.num_outputs * request.quality),
                n=request.num_outputs,
                temperature=request.sampling_temperature,
                frequency_penalty=0.1 if request.avoid_repetition else 0,
                presence_penalty=0.25 if request.avoid_repetition else 0,
            )

        buffer = 100
        text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            chunk_size=GPT3_MAX_ALLOED_TOKENS - request.max_tokens - buffer,
            chunk_overlap=buffer,
        )
        texts = text_splitter.split_text(full_text)
        docs = [Document(page_content=t) for t in texts]

        prompt_template = "{text}\n**********\n" + request.task_instructions.strip()
        state["final_prompt"] = prompt_template
        PROMPT = PromptTemplate(template=prompt_template, input_variables=["text"])

        yield f"Summarizing using {model.value}..."
        chain = load_summarize_chain(
            llm,
            chain_type=request.chain_type,
            map_prompt=PROMPT,
            combine_prompt=PROMPT,
            # verbose=True,
        )
        state["output_text"] = [chain.run(docs).strip()]
