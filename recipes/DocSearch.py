import datetime
import heapq
import io
import math
import os
import re
import subprocess
import tempfile
import typing
from collections import deque

import numpy as np
import pdftotext
import requests
import streamlit as st
from furl import furl
from pydantic import BaseModel
from streamlit.runtime.uploaded_file_manager import UploadedFile

from daras_ai.image_input import upload_st_file
from daras_ai_v2.GoogleGPT import SearchReference, render_outputs, GoogleGPTPage
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import (
    doc_search_settings,
    document_uploader,
)
from daras_ai_v2.gdrive_downloader import (
    gdrive_download,
    is_gdrive_url,
    url_to_gdrive_file_id,
    gdrive_metadata,
)
from daras_ai_v2.language_model import (
    run_language_model,
    get_embeddings,
    LargeLanguageModels,
)
from daras_ai_v2.language_model_settings_widgets import language_model_settings
from daras_ai_v2.loom_video_widget import youtube_video

DEFAULT_DOC_SEARCH_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/assets/DOC%20SEARCH.gif"


class DocSearchPage(BasePage):
    title = "Search your Docs with GPT"
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
    }

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
        sampling_temperature: float | None

        max_references: int | None
        max_context_words: int | None
        scroll_jump: int | None

    class ResponseModel(BaseModel):
        output_text: list[str]

        references: list[SearchReference]
        final_prompt: str

    def render_form_v2(self):
        st.text_area("##### Search Query", key="search_query")
        document_uploader("##### Documents")

    def validate_form_v2(self):
        search_query = st.session_state.get("search_query", "").strip()
        assert search_query, "Please enter a Search Query"

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

    def related_workflows(self) -> list:
        from recipes.EmailFaceInpainting import EmailFaceInpaintingPage
        from recipes.SEOSummary import SEOSummaryPage
        from recipes.VideoBots import VideoBotsPage

        return [
            GoogleGPTPage,
            EmailFaceInpaintingPage,
            SEOSummaryPage,
            VideoBotsPage,
        ]

    def render_output(self):
        render_outputs(st.session_state, 300)

        with st.expander("💁‍♀️ Sources"):
            for idx, ref in enumerate(st.session_state.get("references", [])):
                st.write(f"**{idx + 1}**. [{ref['title']}]({ref['url']})")
                st.text(ref["snippet"])

    def render_example(self, state: dict):
        st.write("**Search Query**")
        st.write("```properties\n" + state.get("search_query", "") + "\n```")
        render_outputs(state, 200)

    def render_settings(self):
        st.text_area(
            "### 👩‍🏫 Task Instructions",
            key="task_instructions",
            height=100,
        )
        st.write("---")

        language_model_settings()
        st.write("---")

        doc_search_settings()

    def preview_image(self, state: dict) -> str | None:
        return DEFAULT_DOC_SEARCH_META_IMG

    def preview_description(self, state: dict) -> str:
        return "Add your PDF, Word, HTML or Text docs, train our AI on them with OpenAI embeddings & vector search and then process results with a GPT3 script. This workflow is perfect for anything NOT in ChatGPT: 250-page compliance PDFs, training manuals, your diary, etc."

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

    def render_usage_guide(self):
        youtube_video("Xe4L_dQ2KvU")

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: DocSearchPage.RequestModel = self.RequestModel.parse_obj(state)

        references = yield from get_top_k_references(request)
        state["references"] = references

        # empty search result, abort!
        if not references:
            raise ValueError(
                f"Your search - {request.search_query} - did not match any documents."
            )

        # add time to prompt
        utcnow = datetime.datetime.utcnow().strftime("%B %d, %Y %H:%M:%S %Z")
        task_instructions = request.task_instructions.replace(
            "{{ datetime.utcnow }}", utcnow
        )
        # add task instructions
        prompt = task_instructions.strip() + "\n\n"
        # add search results to the prompt
        prompt += references_as_prompt(references) + "\n\n"
        # add the question
        prompt += f"Question: {request.search_query}\nAnswer:"
        state["final_prompt"] = prompt

        yield "Generating answer using GPT-3..."
        output_text = run_language_model(
            model=request.selected_model,
            quality=request.quality,
            num_outputs=request.num_outputs,
            temperature=request.sampling_temperature,
            prompt=prompt,
            max_tokens=request.max_tokens,
            avoid_repetition=request.avoid_repetition,
        )
        state["output_text"] = output_text


def get_top_k_references(
    request: DocSearchPage.RequestModel,
) -> typing.Generator[str, None, list[SearchReference]]:
    yield f"Getting query embeddings..."
    query_embeds = get_embeddings_cached(request.search_query)[0]
    yield "Getting document embeddings..."
    input_docs = request.documents or []
    embeds = [
        embeds
        for f_url in input_docs
        for embeds in doc_url_to_embeds(
            f_url=f_url,
            max_context_words=request.max_context_words,
            scroll_jump=request.scroll_jump,
        )
    ]
    yield f"Searching documents..."
    candidates = [
        {**meta, "score": vector_similarity(query_embeds, doc_embeds)}
        for meta, doc_embeds in embeds
    ]
    # apply cutoff
    cutoff = 0.7
    candidates = [match for match in candidates if match["score"] >= cutoff]
    # get top_k best matches
    matches = heapq.nlargest(
        request.max_references, candidates, key=lambda match: match["score"]
    )
    return matches


def references_as_prompt(references: list[SearchReference], sep="\n\n---\n\n") -> str:
    return sep.join(
        f'''\
Search Result: [{idx + 1}]
Title: {ref["title"]}
Snippet: """
{ref["snippet"]}
"""\
'''
        for idx, ref in enumerate(references)
    )


def doc_url_to_embeds(
    *,
    f_url: str,
    max_context_words: int,
    scroll_jump: int,
):
    f = furl(f_url)
    if is_gdrive_url(f):
        # extract filename from google drive metadata
        meta = gdrive_metadata(url_to_gdrive_file_id(f))
        f_name = meta["name"]
        f_etag = meta.get("md5Checksum") or meta.get("modifiedTime")
    else:
        # extract filename from url
        f_name = f.path.segments[-1]
        f_etag = None
    return _doc_url_to_embeds(
        f_url=f_url,
        f_name=f_name,
        f_etag=f_etag,
        max_context_words=max_context_words,
        scroll_jump=scroll_jump,
    )


@st.cache_data(show_spinner=False)
def _doc_url_to_embeds(
    *,
    f_url: str,
    f_name: str,
    f_etag: str | None,  # used as cache key
    max_context_words: int,
    scroll_jump: int,
):
    pages = doc_url_to_text_pages(f_url, f_name)
    # split document into chunks
    chunks = list(document_splitter(pages, max_context_words, scroll_jump))
    texts = [snippet for page_num, snippet in chunks]
    metas = [
        {
            "url": f_url + (f"#page={page}" if len(pages) > 1 else ""),
            "title": f_name,
            "snippet": snippet,
        }
        for page, snippet in chunks
    ]
    # get doc embeds in batches
    embeds = []
    batch_size = 100
    num_batches = math.ceil(len(texts) / batch_size)
    for i in range(num_batches):
        # progress = int(i / num_batches * 100)
        # print(f"Getting document embeddings ({progress}%)...")
        batch = texts[i * batch_size : (i + 1) * batch_size]
        embeds.extend(get_embeddings(batch))
    return zip(metas, embeds)


def doc_url_to_text_pages(f_url: str, f_name: str) -> list[str]:
    f = furl(f_url)
    if is_gdrive_url(f):
        # download from google drive
        f_bytes = gdrive_download(f)
    else:
        # download from url
        f_bytes = requests.get(f_url).content
    # convert document to text
    ext = os.path.splitext(f_name)[-1].lower()
    match ext:
        case ".pdf":
            pages = pdf_to_text_pages(io.BytesIO(f_bytes))
        case ".docx" | ".md" | ".html":
            pages = [pandoc_to_text(f_name, f_bytes)]
        case ".txt" | "":
            pages = [f_bytes.decode()]
        case _:
            raise ValueError(f"Unsupported document format {ext!r} ({f_name})")
    return pages


get_embeddings_cached = st.cache_data(show_spinner=False)(get_embeddings)


def vector_similarity(x: list[float], y: list[float]) -> float:
    """
    Returns the similarity between two vectors.

    Because OpenAI Embeddings are normalized to length 1, the cosine similarity is the same as the dot product.
    """
    return np.dot(np.array(x), np.array(y))


def pdf_to_text_pages(f: typing.BinaryIO) -> list[str]:
    return list(pdftotext.PDF(f))


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


def split_text_into_fragments(text: str):
    # fix word breaks to the next line
    text = word_breaks_re.sub(" - ", text)
    last_idx = 0
    for match in fragment_split_re.finditer(text):
        end_char = match.group(2) or ""
        frag = text[last_idx : match.start()] + end_char
        frag = frag.strip()
        if frag:
            yield frag
        last_idx = match.end()
    yield text[last_idx:]


word_breaks_re = re.compile(
    r"\s*"
    # hypon/en-dash/em-dash
    + r"[\-\–\—]+"
    # followed by whitespace & line break
    + line_break
)


def document_splitter(pages: list[str], max_context_words: int, scroll_jump: int):
    window = deque()
    # split text into fragments
    all_frags = [
        (idx + 1, frag)
        for idx, page in enumerate(pages)
        for frag in split_text_into_fragments(page)
    ]
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
            next_window_words = sum(len(w[1].split()) for w in next_window)
            # next fragment can be safely used without exhausing context, continue expanding
            if next_window_words <= max_context_words:
                continue
        # send off this window as a chunk
        yield window[0][0], "\n".join(w[1] for w in window)
        # scroll jump - remove fragments from the start of window
        for _ in range(scroll_jump):
            try:
                window.popleft()
            except IndexError:
                break
