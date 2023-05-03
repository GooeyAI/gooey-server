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
import pandas as pd
import pdftotext
import requests
import streamlit2 as st
from furl import furl
from googleapiclient.errors import HttpError
from langchain.text_splitter import RecursiveCharacterTextSplitter
from pydantic import BaseModel
from streamlit2 import UploadedFile

from daras_ai.face_restoration import map_parallel
from daras_ai.image_input import upload_st_file, upload_file_from_bytes
from daras_ai_v2.GoogleGPT import SearchReference, render_outputs, GoogleGPTPage
from daras_ai_v2.asr import AsrModels, run_asr, run_google_translate
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import (
    doc_search_settings,
    document_uploader,
    is_user_uploaded_url,
)
from daras_ai_v2.functional import flatten
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
from daras_ai_v2.redis_cache import redis_cache_decorator
from daras_ai_v2.search_ref import apply_response_template

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

        selected_asr_model: typing.Literal[tuple(e.name for e in AsrModels)] | None
        google_translate_target: str | None

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
        render_documents(state)
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

        prompt = ""
        # add time to instructions
        utcnow = datetime.datetime.utcnow().strftime("%B %d, %Y %H:%M:%S %Z")
        task_instructions = request.task_instructions.replace(
            "{{ datetime.utcnow }}", utcnow
        )
        # add search results to the prompt
        prompt += references_as_prompt(references) + "\n\n"
        # add task instructions
        prompt += task_instructions.strip() + "\n\n"
        # add the question
        prompt += f"Question: {request.search_query}\nAnswer:"
        state["final_prompt"] = prompt

        yield f"Generating answer using {LargeLanguageModels[request.selected_model].value}..."
        output_text = run_language_model(
            model=request.selected_model,
            quality=request.quality,
            num_outputs=request.num_outputs,
            temperature=request.sampling_temperature,
            prompt=prompt,
            max_tokens=request.max_tokens,
            avoid_repetition=request.avoid_repetition,
        )
        apply_response_template(output_text, references)
        state["output_text"] = output_text


def get_top_k_references(
    request: DocSearchPage.RequestModel,
) -> typing.Generator[str, None, list[SearchReference]]:
    """
    Get the top k documents that ref the search query

    Args:
        request: the document search request

    Returns:
        the top k documents
    """
    yield f"Getting query embeddings..."
    query_embeds = get_embeddings([request.search_query])[0]
    yield "Getting document embeddings..."
    input_docs = request.documents or []
    nested_embeds: list[list[tuple[SearchReference, list[float]]]] = map_parallel(
        lambda f_url: doc_url_to_embeds(
            f_url=f_url,
            max_context_words=request.max_context_words,
            scroll_jump=request.scroll_jump,
            selected_asr_model=request.selected_asr_model,
            google_translate_target=request.google_translate_target,
        ),
        input_docs,
    )
    embeds: list[tuple[SearchReference, list[float]]] = flatten(nested_embeds)
    yield f"Searching documents..."
    # get all matches above cutoff based on cosine similarity
    cutoff = 0.7
    candidates = [
        {**ref, "score": score}
        for ref, doc_embeds in embeds
        if (score := vector_similarity(query_embeds, doc_embeds)) >= cutoff
    ]
    # get top_k best matches
    matches = heapq.nlargest(
        request.max_references, candidates, key=lambda match: match["score"]
    )
    return matches


def references_as_prompt(references: list[SearchReference], sep="\n\n") -> str:
    """
    Convert a list of references to a prompt containing the formatted search results.

    Args:
        references: list of references
        sep: separator between references in the prompt

    Returns:
        prompt string
    """
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
    selected_asr_model: str = None,
    google_translate_target: str = None,
) -> list[tuple[SearchReference, list[float]]]:
    """
    Get document embeddings for a given document url.

    Args:
        f_url: document url
        max_context_words: max number of words to include in each chunk
        scroll_jump: number of words to scroll by
        google_translate_target: target language for google translate
        selected_asr_model: selected ASR model (used for audio files)

    Returns:
        list of (SearchReference, embeddings vector) tuples
    """
    doc_meta = doc_url_to_metadata(f_url)
    return _doc_url_to_embeds_cached(
        f_url=f_url,
        doc_meta=doc_meta,
        max_context_words=max_context_words,
        scroll_jump=scroll_jump,
        selected_asr_model=selected_asr_model,
        google_translate_target=google_translate_target,
    )


class DocMetadata(typing.NamedTuple):
    name: str
    etag: str | None
    mime_type: str | None


def doc_url_to_metadata(f_url: str) -> DocMetadata:
    """
    Fetches the google drive metadata for a document url

    Args:
        f_url: document url

    Returns:
        document metadata
    """
    f = furl(f_url)
    if is_gdrive_url(f):
        # extract filename from google drive metadata
        try:
            meta = gdrive_metadata(url_to_gdrive_file_id(f))
        except HttpError as e:
            if e.status_code == 404:
                raise FileNotFoundError(
                    f"Could not download the google doc at {f_url} "
                    f"Please make sure to make the document public for viewing."
                ) from e
            else:
                raise
        name = meta["name"]
        etag = meta.get("md5Checksum") or meta.get("modifiedTime")
        mime_type = meta["mimeType"]
    else:
        # extract filename from url
        name = f.path.segments[-1]
        etag = None
        mime_type = None
    return DocMetadata(name, etag, mime_type)


@redis_cache_decorator
# @st.cache_data(show_spinner=False)
def _doc_url_to_embeds_cached(
    *,
    f_url: str,
    doc_meta: DocMetadata,
    max_context_words: int,
    scroll_jump: int,
    google_translate_target: str = None,
    selected_asr_model: str = None,
) -> list[tuple[SearchReference, list[float]]]:
    """
    Get document embeddings for a given document url.

    Args:
        f_url: document url
        doc_meta: document metadata
        max_context_words: max number of words to include in each chunk
        scroll_jump: number of words to scroll by
        google_translate_target: target language for google translate
        selected_asr_model: selected ASR model (used for audio files)

    Returns:
        list of (metadata, embeddings) tuples
    """
    pages = doc_url_to_text_pages(
        f_url=f_url,
        doc_meta=doc_meta,
        selected_asr_model=selected_asr_model,
        google_translate_target=google_translate_target,
    )
    metas: list[SearchReference]
    if isinstance(pages, pd.DataFrame):
        text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            chunk_size=int(max_context_words / 0.75),
            chunk_overlap=int(max_context_words / 0.75 / 5),
        )
        metas = [
            {
                "title": doc_meta.name,
                "url": f_url,
                **row,
                "score": -1,
                "snippet": snippet,
            }
            for idx, row in pages.iterrows()
            for snippet in text_splitter.split_text(row["snippet"])
        ]
    else:
        # split document into chunks
        chunks = list(document_splitter(pages, max_context_words, scroll_jump))
        metas = [
            {
                "title": doc_meta.name + (f" - Page {page}" if len(pages) > 1 else ""),
                "url": f_url + (f"#page={page}" if len(pages) > 1 else ""),
                "snippet": snippet,
                "score": -1,
            }
            for page, snippet in chunks
        ]
    # get doc embeds in batches
    embeds = []
    batch_size = 100
    texts = [m["title"] + "\n\n" + m["snippet"] for m in metas]
    for i in range(0, len(texts), batch_size):
        # progress = int(i / len(texts) * 100)
        # print(f"Getting document embeddings ({progress}%)...")
        batch = texts[i : i + batch_size]
        embeds.extend(get_embeddings(batch))
    return list(zip(metas, embeds))


@redis_cache_decorator
# @st.cache_data(show_spinner=False)
def doc_url_to_text_pages(
    *,
    f_url: str,
    doc_meta: DocMetadata,
    google_translate_target: str | None,
    selected_asr_model: str | None,
) -> list[str]:
    """
    Download document from url and convert to text pages.

    Args:
        f_url: url of document
        doc_meta: document metadata
        google_translate_target: target language for google translate
        selected_asr_model: selected ASR model (used for audio files)

    Returns:
        list of text pages
    """
    f = furl(f_url)
    f_name = doc_meta.name
    if is_gdrive_url(f):
        # download from google drive
        f_bytes, ext = gdrive_download(f, doc_meta.mime_type)
    else:
        # download from url
        f_bytes = requests.get(f_url).content
        # get extension from filename, defaulting to html (useful for URLs)
        ext = os.path.splitext(f_name)[-1].lower() or ".html"
    # convert document to text pages
    match ext:
        case ".pdf":
            pages = pdf_to_text_pages(io.BytesIO(f_bytes))
        case ".docx" | ".md" | ".html" | ".rtf" | ".epub" | ".odt":
            pages = [pandoc_to_text(f_name + ext, f_bytes)]
        case ".txt":
            pages = [f_bytes.decode()]
        case ".wav" | ".ogg" | ".mp3" | ".aac":
            if not selected_asr_model:
                raise ValueError(
                    "For transcribing audio/video, please choose an ASR model from the settings!"
                )
            if is_gdrive_url(f):
                f_url = upload_file_from_bytes(
                    f_name, f_bytes, content_type=doc_meta.mime_type
                )
            pages = [run_asr(f_url, selected_model=selected_asr_model, language="en")]
        case ".csv" | ".xlsx" | ".tsv" | ".ods":
            df = pd.read_csv(io.BytesIO(f_bytes), dtype=str).dropna()
            assert (
                "snippet" in df.columns
            ), f'uploaded spreadsheet must contain a "snippet" column - {f_name !r}'
            pages = df
        case _:
            raise ValueError(f"Unsupported document format {ext!r} ({f_name})")
    # optionally, translate text
    if google_translate_target:
        pages = run_google_translate(pages, google_translate_target)
    return pages


def vector_similarity(x: list[float], y: list[float]) -> float:
    """
    Returns the similarity between two vectors.

    Because OpenAI Embeddings are normalized to length 1, the cosine similarity is the same as the dot product.
    """
    return np.dot(np.array(x), np.array(y))


def pdf_to_text_pages(f: typing.BinaryIO) -> list[str]:
    return list(pdftotext.PDF(f))


def pandoc_to_text(f_name: str, f_bytes: bytes, to="plain") -> str:
    """
    Convert document to text using pandoc.

    Args:
        f_name: filename of document
        f_bytes: document bytes
        to: pandoc output format (default: plain)

    Returns:
        extracted text content of document
    """
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


def document_splitter(
    pages: list[str],
    max_context_words: int,
    scroll_jump: int,
) -> typing.Generator[tuple[int, str], None, None]:
    """
    Split document into chunks of text.
    Each chunk is built iteratively by adding fragments to the current chunk until the max_context_words is reached.

    Args:
        pages: list of text pages
        max_context_words: maximum number of words in each chunk
        scroll_jump: number of fragments to jump when scrolling

    Returns:
        generator of (page number, fragment) tuples
    """
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


def render_documents(state, label="**Documents**", *, key="documents"):
    documents = state.get(key, [])
    if not documents:
        return
    st.write(label)
    for doc in documents:
        if is_user_uploaded_url(doc):
            f = furl(doc)
            filename = f.path.segments[-1]
        else:
            filename = doc
        st.write(f"🔗[*{filename}*]({doc})")
