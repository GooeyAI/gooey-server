import codecs
import heapq
import io
import random
import subprocess
import tempfile
import typing

import numpy as np
import requests
from furl import furl
from googleapiclient.errors import HttpError
from pydantic import BaseModel

import gooey_ui as gui
from daras_ai.image_input import (
    upload_file_from_bytes,
    safe_filename,
    guess_ext_from_response,
    get_mimetype_from_response,
)
from daras_ai_v2 import settings
from daras_ai_v2.asr import AsrModels, run_asr, run_google_translate
from daras_ai_v2.doc_search_settings_widgets import (
    is_user_uploaded_url,
)
from daras_ai_v2.fake_user_agents import FAKE_USER_AGENTS
from daras_ai_v2.functional import flatmap_parallel
from daras_ai_v2.gdrive_downloader import (
    gdrive_download,
    is_gdrive_url,
    url_to_gdrive_file_id,
    gdrive_metadata,
)
from daras_ai_v2.language_model import (
    openai_embedding_create,
)
from daras_ai_v2.redis_cache import redis_cache_decorator
from daras_ai_v2.search_ref import (
    SearchReference,
    remove_quotes,
)
from daras_ai_v2.text_splitter import text_splitter


class DocSearchRequest(BaseModel):
    search_query: str
    documents: list[str] | None

    max_references: int | None
    max_context_words: int | None
    scroll_jump: int | None

    selected_asr_model: typing.Literal[tuple(e.name for e in AsrModels)] | None
    google_translate_target: str | None


def get_top_k_references(
    request: DocSearchRequest,
) -> typing.Generator[str, None, list[SearchReference]]:
    """
    Get the top k documents that ref the search query

    Args:
        request: the document search request

    Returns:
        the top k documents
    """
    yield "Getting embeddings..."
    query_embeds = openai_embedding_create([request.search_query])[0]
    input_docs = request.documents or []
    embeds: list[tuple[SearchReference, np.ndarray]] = flatmap_parallel(
        lambda f_url: doc_url_to_embeds(
            f_url=f_url,
            max_context_words=request.max_context_words,
            scroll_jump=request.scroll_jump,
            selected_asr_model=request.selected_asr_model,
            google_translate_target=request.google_translate_target,
        ),
        input_docs,
    )

    yield "Searching documents..."
    # get all matches above cutoff based on cosine similarity
    cutoff = 0.7
    candidates = [
        {**ref, "score": score}
        for ref, doc_embeds in embeds
        if (score := query_embeds.dot(doc_embeds)) >= cutoff
    ]
    # get top_k best matches
    references = heapq.nlargest(
        request.max_references, candidates, key=lambda match: match["score"]
    )

    # merge duplicate references
    uniques = {}
    for ref in references:
        key = ref["url"]
        try:
            existing = uniques[key]
        except KeyError:
            uniques[key] = ref
        else:
            existing["snippet"] += "\n\n...\n\n" + ref["snippet"]
            existing["score"] = (existing["score"] + ref["score"]) / 2
    return list(uniques.values())


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
Title: """{remove_quotes(ref["title"])}"""
Snippet: """
{remove_quotes(ref["snippet"])}
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
) -> list[tuple[SearchReference, np.ndarray]]:
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
    return get_embeds_for_doc(
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
    f = furl(f_url.strip("/"))
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
        try:
            r = requests.head(
                f_url,
                headers={"User-Agent": random.choice(FAKE_USER_AGENTS)},
                timeout=settings.EXTERNAL_REQUEST_TIMEOUT_SEC,
            )
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"ignore error while downloading {f_url}: {e}")
            mime_type = None
            etag = None
            name = None
        else:
            mime_type = get_mimetype_from_response(r)
            etag = r.headers.get("etag", r.headers.get("last-modified"))
            name = (
                r.headers.get("content-disposition", "")
                .split("filename=")[-1]
                .strip('"')
            )
    # extract filename from url as a fallback
    if not name:
        if is_user_uploaded_url(str(f)):
            name = f.path.segments[-1]
        else:
            name = f"{f.host}{f.path}"
    return DocMetadata(name, etag, mime_type)


@redis_cache_decorator
def get_embeds_for_doc(
    *,
    f_url: str,
    doc_meta: DocMetadata,
    max_context_words: int,
    scroll_jump: int,
    google_translate_target: str = None,
    selected_asr_model: str = None,
) -> list[tuple[SearchReference, np.ndarray]]:
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
    import pandas as pd

    pages = doc_url_to_text_pages(
        f_url=f_url,
        doc_meta=doc_meta,
        selected_asr_model=selected_asr_model,
        google_translate_target=google_translate_target,
    )
    chunk_size = int(max_context_words * 2)
    chunk_overlap = int(max_context_words * 2 / scroll_jump)
    metas: list[SearchReference]
    # split the text into chunks
    if isinstance(pages, pd.DataFrame):
        metas = [
            {
                "title": doc_meta.name,
                "url": f_url,
                **row,  # preserve extra csv rows
                "score": -1,
                "snippet": doc.text,
            }
            for idx, row in pages.iterrows()
            for doc in text_splitter(
                row["snippet"], chunk_size=chunk_size, chunk_overlap=chunk_overlap
            )
        ]
    else:
        metas = [
            {
                "title": doc_meta.name
                + (f" - Page {doc.end + 1}" if len(pages) > 1 else ""),
                "url": furl(f_url)
                .set(fragment_args={"page": doc.end + 1} if len(pages) > 1 else {})
                .url,
                "snippet": doc.text,
                "score": -1,
            }
            for doc in text_splitter(
                pages, chunk_size=chunk_size, chunk_overlap=chunk_overlap
            )
        ]
    # get doc embeds in batches
    embeds = []
    batch_size = 100
    texts = [m["title"] + " | " + m["snippet"] for m in metas]
    for i in range(0, len(texts), batch_size):
        # progress = int(i / len(texts) * 100)
        # print(f"Getting document embeddings ({progress}%)...")
        batch = texts[i : i + batch_size]
        embeds.extend(openai_embedding_create(batch))
    return list(zip(metas, embeds))


@redis_cache_decorator
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
        try:
            r = requests.get(
                f_url,
                headers={"User-Agent": random.choice(FAKE_USER_AGENTS)},
                timeout=settings.EXTERNAL_REQUEST_TIMEOUT_SEC,
            )
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"ignore error while downloading {f_url}: {e}")
            return []
        f_bytes = r.content
        # if it's a known encoding, standardize to utf-8
        if r.encoding:
            try:
                codec = codecs.lookup(r.encoding)
            except LookupError:
                pass
            else:
                f_bytes = codec.decode(f_bytes)[0].encode()
        ext = guess_ext_from_response(r)
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
            import pandas as pd

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


def pdf_to_text_pages(f: typing.BinaryIO) -> list[str]:
    import pdftotext

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
        tempfile.NamedTemporaryFile("wb", suffix="." + safe_filename(f_name)) as infile,
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
        print("\t$ " + " ".join(args))
        subprocess.check_call(args)
        return outfile.read()

        refs = st.session_state.get("references", [])
        if not refs:
            return


def render_sources_widget(refs: list[SearchReference]):
    if not refs:
        return
    with gui.expander("💁‍♀️ Sources"):
        for idx, ref in enumerate(refs):
            gui.html(
                # language=HTML
                f"""<p>{idx + 1}. <a href="{ref['url']}" target="_blank">{ref['title']}</a></p>""",
            )
            gui.text(ref["snippet"], style={"maxHeight": "200px"})
        gui.write(
            "---\n"
            + "```text\n"
            + "\n".join(f"[{idx + 1}] {ref['url']}" for idx, ref in enumerate(refs))
            + "\n```",
            height=200,
            disabled=True,
        )
