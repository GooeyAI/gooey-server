import datetime
import heapq
import io
import os
import re
import subprocess
import tempfile
import typing
from collections import deque

import numpy as np
import openai
import pdftotext
import requests
import streamlit as st
from furl import furl
from pydantic import BaseModel
from streamlit.runtime.uploaded_file_manager import UploadedFile

from daras_ai.face_restoration import map_parallel
from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2 import settings
from daras_ai_v2.GoogleGPT import SearchReference, render_outputs
from daras_ai_v2.base import BasePage
from daras_ai_v2.language_model import run_language_model
from daras_ai_v2.language_model_settings_widgets import language_model_settings


class DocSearchPage(BasePage):
    title = " Search Documents using GPT"
    slug_versions = ["doc-search"]

    sane_defaults = dict(
        sampling_temperature=0.1,
        max_tokens=256,
        num_outputs=1,
        quality=1.0,
        max_references=3,
        max_context_words=200,
        scroll_jump=5,
        avoid_repetition=True,
    )

    class RequestModel(BaseModel):
        search_query: str
        documents: list[str] | None
        # selected_model: typing.Literal[
        #     tuple(e.name for e in LargeLanguageModels)
        # ] | None

        task_instructions: str | None

        avoid_repetition: bool | None
        num_outputs: int | None
        quality: float | None
        max_tokens: int | None
        sampling_temperature: float | None

        max_references: int | None
        max_context_words: int | None
        scroll_jump: int | None

    class ResponseModel(BaseModel):
        output_text: list[str]

        references: list[SearchReference]
        final_prompt: str

    def render_form_v2(self):
        st.text_input("##### Search Query", key="search_query")
        st.file_uploader(
            "##### Documents",
            key="__document_files",
            upload_key="documents",
            type=["pdf", "txt", "docx", "md"],
            accept_multiple_files=True,
        )

    def validate_form_v2(self):
        search_query = st.session_state.get("search_query", "").strip()
        assert search_query, "Please enter a Search Query"

        document_files: list[UploadedFile] | None = st.session_state.get(
            "__document_files"
        )
        if document_files:
            st.session_state["documents"] = [
                upload_file_from_bytes(f.name, f.getvalue(), f.type)
                for f in document_files
            ]

        assert st.session_state.get("documents"), "Please provide at least 1 Document"

    def render_output(self):
        render_outputs(st.session_state, 300)

        with st.expander("Sources"):
            for idx, ref in enumerate(st.session_state.get("references", [])):
                st.write(f"**{idx + 1}**. [{ref['title']}]({ref['url']})")
                st.text(ref["snippet"])

    def render_example(self, state: dict):
        st.write("**Search Query**")
        st.write("```properties\n" + state.get("search_query", "") + "\n```")
        render_outputs(state, 200)

    def render_settings(self):
        st.text_area(
            "### Task Instructions",
            key="task_instructions",
            height=100,
        )
        st.write("---")

        language_model_settings()
        st.write("---")

        st.write("### 🔎m Search Settings")
        st.number_input(
            label="""
##### Max References
The maximum number of References to include from the source document.
            """,
            key="max_references",
            min_value=1,
            max_value=10,
        )

        st.number_input(
            label="""
##### Max context size (in words)

The maximum size of each split of the document.\\
A high context size allows GPT to access a greater chunk of information from the source document, 
at the cost of being too verbose, and running out of input tokens. 
            """,
            key="max_context_words",
            min_value=10,
            max_value=500,
        )

        st.number_input(
            label="""
##### Scroll Jump
We split the documents into chunks by scrolling through it.\\
If scroll jump is too high, there might not be enough overlap between the chunks to answer the questions accurately.
""",
            key="scroll_jump",
            min_value=1,
            max_value=50,
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
        request: DocSearchPage.RequestModel = self.RequestModel.parse_obj(state)

        yield "Reading documents..."
        rows = []
        for f_url in request.documents or []:
            f_name, pages = doc_url_to_text_pages(f_url)
            full_text = "\n\n".join(pages)
            # fix word breaks to the next line
            full_text = word_breaks_re.sub(" - ", full_text)
            # split document into chunks
            for snippet in document_splitter(full_text, request):
                rows.append({"url": f_url, "title": f_name, "snippet": snippet})

        yield "Getting document embeddings..."
        docs = [c["snippet"] for c in rows]
        similarities = get_document_similarities(
            request.search_query, docs, request.max_references
        )
        # empty search result, abort!
        if not similarities:
            raise ValueError(
                f"Your search - {request.search_query} - did not match any documents."
            )
        # convert similarities to references
        state["references"] = [
            {
                **rows[idx],
                "score": score,
            }
            for idx, (_, score) in enumerate(similarities)
        ]

        # add time to prompt
        utcnow = datetime.datetime.utcnow().strftime("%B %d, %Y %H:%M:%S %Z")
        task_instructions = request.task_instructions.replace(
            "{{ datetime.utcnow }}", utcnow
        )
        # add task instructions
        prompt = task_instructions.strip() + "\n\n"
        # add search results to the prompt
        search_results = "\n\n---\n\n".join(
            f'''Search Result: [{idx + 1}]\nTitle: {rows[doc_idx]["title"]}\nSnippet: """\n{rows[doc_idx]["snippet"]}"""'''
            for idx, (doc_idx, _) in enumerate(similarities)
        )
        prompt += f"\n{search_results}\n\n"
        # add the question
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


@st.cache_data
def doc_url_to_text_pages(f_url: str) -> (str, list[str]):
    # get document data from url
    f_name = furl(f_url).path.segments[-1]
    f_bytes = requests.get(f_url).content
    # convert document to text
    ext = os.path.splitext(f_name)[-1].lower()
    match ext:
        case ".pdf":
            pages = pdf_to_text_pages(io.BytesIO(f_bytes))
        case ".docx" | ".md":
            pages = [pandoc_to_text(f_name, f_bytes)]
        case ".txt":
            pages = [f_bytes.decode()]
        case _:
            raise ValueError(f"Unsupported document format {ext!r}")
    return f_name, pages


def get_document_similarities(
    query: str, docs: list[str], n: int, cutoff: float = 0.7
) -> list[(float, int)]:
    query_embedding = get_embedding(query)
    embeddings = map_parallel(get_embedding, docs)
    similarities = [
        (vector_similarity(query_embedding, doc_embedding), doc_index)
        for doc_index, doc_embedding in enumerate(embeddings)
    ]
    similarities = [(i, s) for s, i in similarities if s >= cutoff]
    return heapq.nlargest(n, similarities)


@st.cache_data(show_spinner=False)
def get_embedding(text: str) -> list[float]:
    openai.api_key = settings.OPENAI_API_KEY
    result = openai.Embedding.create(model="text-embedding-ada-002", input=text)
    return result["data"][0]["embedding"]


def vector_similarity(x: list[float], y: list[float]) -> float:
    """
    Returns the similarity between two vectors.

    Because OpenAI Embeddings are normalized to length 1, the cosine similarity is the same as the dot product.
    """
    return np.dot(np.array(x), np.array(y))


# @st.cache_data()
def pdf_to_text_pages(f: typing.BinaryIO) -> list[str]:
    return list(pdftotext.PDF(f))


# @st.cache_data()
def pandoc_to_text(f_name: str, f_bytes: bytes, to="plain") -> str:
    with (
        tempfile.NamedTemporaryFile("wb", suffix="." + f_name) as infile,
        tempfile.NamedTemporaryFile("r") as outfile,
    ):
        infile.write(f_bytes)
        args = [
            "pandoc",
            "--standalone",
            infile.name,
            "--to",
            to,
            "--output",
            outfile.name,
        ]
        print("\t$", " ".join(args))
        subprocess.check_call(args)
        return outfile.read()


# language=regexp
line_break = r"\s*[\r\n\f\v]\s*"

# split long text at sentence ends
fragment_split_re = re.compile(
    r"("
    # whitespace & line break
    + line_break
    # OR
    + r"|"
    # sentence end chars
    + r"s*([\.\!\?])"
    + r")"
    # followed by whitespace & line break
    + line_break
)


def split_text_into_fragments(text):
    last_idx = 0
    for match in fragment_split_re.finditer(text):
        end_char = match.group(2) or ""
        frag = text[last_idx : match.start()] + end_char
        frag = frag.strip()
        if frag:
            yield frag
        last_idx = match.end()


word_breaks_re = re.compile(
    r"\s*"
    # hypon/en-dash/em-dash
    + r"[\-\–\—]+"
    # followed by whitespace & line break
    + line_break
)


def document_splitter(full_text, request):
    window = deque()
    # split text into fragments
    all_frags = list(split_text_into_fragments(full_text))
    for idx in range(len(all_frags)):
        # add this fragment to the window
        window.append(all_frags[idx])
        # keep increasing the window until your either reach the end, or the context size is exhausted
        try:
            next_frag = all_frags[idx + 1]
        except IndexError:
            pass
        else:
            # calculate the size of window + next fragment
            next_window = [*window, next_frag]
            next_window_words = sum(len(re.split("\s+", para)) for para in next_window)
            # next fragment can be safely used without exhausing context, continue expanding
            if next_window_words <= request.max_context_words:
                continue
        # send off this window as a chunk
        yield "\n".join(window)
        # scroll jump - remove fragments from the start of window
        for _ in range(request.scroll_jump):
            try:
                window.popleft()
            except IndexError:
                break
