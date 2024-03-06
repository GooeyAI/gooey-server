import codecs
import csv
import io
import mimetypes
import random
import re
import tempfile
import typing

import numpy as np
import requests
from furl import furl
from loguru import logger
from pydantic import BaseModel, Field
from rank_bm25 import BM25Okapi

import gooey_ui as gui
from daras_ai.image_input import (
    upload_file_from_bytes,
    safe_filename,
    get_mimetype_from_response,
)
from daras_ai_v2 import settings
from daras_ai_v2.asr import (
    AsrModels,
    run_asr,
    run_google_translate,
    download_youtube_to_wav,
)
from daras_ai_v2.azure_doc_extract import (
    table_arr_to_prompt_chunked,
    THEAD,
    azure_doc_extract_page_num,
)
from daras_ai_v2.doc_search_settings_widgets import (
    is_user_uploaded_url,
)
from daras_ai_v2.exceptions import raise_for_status, call_cmd, UserError
from daras_ai_v2.fake_user_agents import FAKE_USER_AGENTS
from daras_ai_v2.functional import (
    flatmap_parallel,
    map_parallel,
)
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
from daras_ai_v2.text_splitter import text_splitter, puncts, Document
from files.models import FileMetadata


class DocSearchRequest(BaseModel):
    search_query: str
    keyword_query: str | list[str] | None

    documents: list[str] | None

    max_references: int | None
    max_context_words: int | None
    scroll_jump: int | None

    doc_extract_url: str | None

    dense_weight: float | None = Field(
        ge=0.0,
        le=1.0,
        title="Dense Embeddings Weightage",
        description="""
Weightage for dense vs sparse embeddings. `0` for sparse, `1` for dense, `0.5` for equal weight.
Generally speaking, dense embeddings excel at understanding the context of the query, whereas sparse vectors excel at keyword matches.
        """,
    )


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
    from recipes.BulkRunner import url_to_runs

    yield "Fetching latest knowledge docs..."
    input_docs = request.documents or []

    if request.doc_extract_url:
        page_cls, sr, pr = url_to_runs(request.doc_extract_url)
        selected_asr_model = sr.state.get("selected_asr_model")
        google_translate_target = sr.state.get("google_translate_target")
    else:
        selected_asr_model = google_translate_target = None

    file_url_metas = flatmap_parallel(doc_or_yt_url_to_metadatas, input_docs)
    file_urls, file_metas = zip(*file_url_metas)

    yield "Creating knowledge embeddings..."
    embeds: list[tuple[SearchReference, np.ndarray]] = flatmap_parallel(
        lambda f_url, file_meta: get_embeds_for_doc(
            f_url=f_url,
            doc_meta=DocMetadata.from_file_metadata(file_meta),
            max_context_words=request.max_context_words,
            scroll_jump=request.scroll_jump,
            selected_asr_model=selected_asr_model,
            google_translate_target=google_translate_target,
        ),
        file_urls,
        file_metas,
    )
    if not embeds:
        return []
    dense_query_embeds = openai_embedding_create([request.search_query])[0]

    yield "Searching knowledge base..."

    dense_weight = request.dense_weight
    if dense_weight is None:  # for backwards compatibility
        dense_weight = 1
    sparse_weight = 1 - dense_weight

    if dense_weight:
        from scipy.stats import rankdata

        # get dense scores above cutoff based on cosine similarity
        cutoff = 0.7
        custom_weights = np.array(
            [float(ref.get("weight") or "1") for ref, _ in embeds]
        )

        dense_scores = np.dot(
            [doc_embeds for _, doc_embeds in embeds], dense_query_embeds
        )
        dense_scores *= custom_weights
        dense_scores[dense_scores < cutoff] = 0.0
        dense_ranks = rankdata(-dense_scores, method="max")
    else:
        dense_ranks = np.zeros(len(embeds))

    if sparse_weight:
        yield "Considering results..."
        # get sparse scores
        bm25_corpus = flatmap_parallel(
            lambda f_url, file_meta: get_bm25_embeds_for_doc(
                f_url=f_url,
                doc_meta=DocMetadata.from_file_metadata(file_meta),
                max_context_words=request.max_context_words,
                scroll_jump=request.scroll_jump,
                selected_asr_model=selected_asr_model,
                google_translate_target=google_translate_target,
            ),
            file_urls,
            file_metas,
        )
        bm25 = BM25Okapi(bm25_corpus, k1=2, b=0.3)
        if request.keyword_query and isinstance(request.keyword_query, list):
            sparse_query_tokenized = [item.lower() for item in request.keyword_query]
        else:
            sparse_query_tokenized = bm25_tokenizer(
                request.keyword_query or request.search_query
            )
        if sparse_query_tokenized:
            sparse_scores = np.array(bm25.get_scores(sparse_query_tokenized))
            # sparse_scores *= custom_weights
            sparse_ranks = rankdata(-sparse_scores, method="max")
        else:
            sparse_ranks = np.zeros(len(embeds))
    else:
        sparse_ranks = np.zeros(len(embeds))

    # just in case sparse and dense ranks are different lengths, truncate to the shorter one
    if len(sparse_ranks) != len(dense_ranks):
        logger.warning(
            f"sparse and dense ranks are different lengths, truncating... {len(sparse_ranks)=} {len(dense_ranks)=} {len(embeds)=}"
        )
        sparse_ranks = sparse_ranks[: len(dense_ranks)]
        dense_ranks = dense_ranks[: len(sparse_ranks)]
    # RRF formula: 1 / (k + rank)
    k = 60
    rrf_scores = (
        sparse_weight / (k + sparse_ranks) + dense_weight / (k + dense_ranks)
    ) * k

    # Final ranking
    max_references = min(request.max_references, len(rrf_scores))
    top_k = np.argpartition(rrf_scores, -max_references)[-max_references:]
    final_ranks = sorted(top_k, key=rrf_scores.__getitem__, reverse=True)

    references = [embeds[idx][0] | {"score": rrf_scores[idx]} for idx in final_ranks]

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


bm25_split_re = re.compile(rf"[{puncts},|\s]")


def bm25_tokenizer(text: str) -> list[str]:
    return [t for t in bm25_split_re.split(text.lower()) if t]


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


class DocMetadata(typing.NamedTuple):
    name: str
    etag: str | None
    mime_type: str | None

    @classmethod
    def from_file_metadata(cls, meta: FileMetadata):
        return cls(meta.name, meta.etag, meta.mime_type)


def doc_or_yt_url_to_metadatas(f_url: str) -> list[tuple[str, FileMetadata]]:
    if is_yt_url(f_url):
        entries = yt_dlp_get_video_entries(f_url)
        return [
            (
                entry["webpage_url"],
                FileMetadata(
                    name=entry.get("title", "YouTube Video"),
                    # youtube doesn't provide etag, so we use filesize_approx or upload_date
                    etag=entry.get("filesize_approx") or entry.get("upload_date"),
                    # we will later convert & save as wav
                    mime_type="audio/wav",
                    total_bytes=entry.get("filesize_approx", 0),
                ),
            )
            for entry in entries
        ]
    else:
        return [(f_url, doc_url_to_file_metadata(f_url))]


def doc_url_to_file_metadata(f_url: str) -> FileMetadata:
    from googleapiclient.errors import HttpError

    f = furl(f_url.strip("/"))
    if is_gdrive_url(f):
        # extract filename from google drive metadata
        try:
            meta = gdrive_metadata(url_to_gdrive_file_id(f))
        except HttpError as e:
            if e.status_code == 404:
                raise UserError(
                    f"Could not download the google doc at {f_url} "
                    f"Please make sure to make the document public for viewing."
                ) from e
            else:
                raise
        name = meta["name"]
        etag = meta.get("md5Checksum") or meta.get("modifiedTime")
        mime_type = meta["mimeType"]
        total_bytes = int(meta.get("size") or 0)
    else:
        try:
            r = requests.head(
                f_url,
                headers={"User-Agent": random.choice(FAKE_USER_AGENTS)},
                timeout=settings.EXTERNAL_REQUEST_TIMEOUT_SEC,
            )
            raise_for_status(r)
        except requests.RequestException as e:
            print(f"ignore error while downloading {f_url}: {e}")
            name = None
            mime_type = None
            etag = None
            total_bytes = 0
        else:
            name = (
                r.headers.get("content-disposition", "")
                .split("filename=")[-1]
                .strip('"')
            )
            etag = r.headers.get("etag", r.headers.get("last-modified"))
            mime_type = get_mimetype_from_response(r)
            total_bytes = int(r.headers.get("content-length") or 0)
    # extract filename from url as a fallback
    if not name:
        if is_user_uploaded_url(str(f)):
            name = f.path.segments[-1]
        else:
            name = f"{f.host}{f.path}"
    # guess mimetype from name as a fallback
    if not mime_type:
        mime_type = mimetypes.guess_type(name)[0]
    return FileMetadata(
        name=name, etag=etag, mime_type=mime_type, total_bytes=total_bytes
    )


def yt_dlp_get_video_entries(url: str) -> list[dict]:
    data = yt_dlp_extract_info(url)
    entries = data.get("entries", [data])
    return [e for e in entries if e]


def yt_dlp_extract_info(url: str) -> dict:
    import yt_dlp

    # https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/options.py
    params = dict(ignoreerrors=True, check_formats=False)
    with yt_dlp.YoutubeDL(params) as ydl:
        data = ydl.extract_info(url, download=False)
        if not data:
            raise UserError(
                f"Could not download the youtube video at {url!r}. "
                f"Please make sure the video is public and the url is correct."
            )
        return data


@redis_cache_decorator
def get_bm25_embeds_for_doc(
    *,
    f_url: str,
    doc_meta: DocMetadata,
    max_context_words: int,
    scroll_jump: int,
    google_translate_target: str = None,
    selected_asr_model: str = None,
):
    pages = doc_url_to_text_pages(
        f_url=f_url,
        doc_meta=doc_meta,
        selected_asr_model=selected_asr_model,
    )
    refs = pages_to_split_refs(
        pages=pages,
        f_url=f_url,
        doc_meta=doc_meta,
        max_context_words=max_context_words,
        scroll_jump=scroll_jump,
    )
    translate_split_refs(refs, google_translate_target)
    tokenized_corpus = [
        bm25_tokenizer(ref["title"]) + bm25_tokenizer(ref["snippet"]) for ref in refs
    ]
    return tokenized_corpus


def translate_split_refs(
    refs: list[SearchReference], google_translate_target: str | None
):
    if not google_translate_target:
        return
    snippets = [ref["snippet"] for ref in refs]
    translated_snippets = run_google_translate(snippets, google_translate_target)
    for ref, translated_snippet in zip(refs, translated_snippets):
        ref["snippet"] = translated_snippet


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
    pages = doc_url_to_text_pages(
        f_url=f_url,
        doc_meta=doc_meta,
        selected_asr_model=selected_asr_model,
    )
    refs = pages_to_split_refs(
        pages=pages,
        f_url=f_url,
        doc_meta=doc_meta,
        max_context_words=max_context_words,
        scroll_jump=scroll_jump,
    )
    translate_split_refs(refs, google_translate_target)
    texts = [m["title"] + " | " + m["snippet"] for m in refs]
    # get doc embeds in batches
    batch_size = 16  # azure openai limits
    embeds = flatmap_parallel(
        openai_embedding_create,
        [texts[i : i + batch_size] for i in range(0, len(texts), batch_size)],
        max_workers=2,
    )
    return list(zip(refs, embeds))


def pages_to_split_refs(
    *,
    pages,
    f_url: str,
    doc_meta: DocMetadata,
    max_context_words: int,
    scroll_jump: int,
) -> list[SearchReference]:
    import pandas as pd

    chunk_size = int(max_context_words * 2)
    chunk_overlap = int(max_context_words * 2 / scroll_jump)
    if isinstance(pages, pd.DataFrame):
        refs = []
        # treat each row as a separate document
        for idx, row in pages.iterrows():
            row = dict(row)
            sections = (row.pop("sections", "") or "").strip()
            snippet = (row.pop("snippet", "") or "").strip()
            if sections:
                splits = split_sections(
                    sections, chunk_size=chunk_size, chunk_overlap=chunk_overlap
                )
            elif snippet:
                splits = text_splitter(
                    snippet, chunk_size=chunk_size, chunk_overlap=chunk_overlap
                )
            else:
                continue
            refs += [
                {
                    "title": doc_meta.name,
                    "url": f_url,
                    **row,  # preserve extra csv rows
                    "snippet": doc.text,
                    **doc.kwargs,
                    "score": -1,
                }
                for doc in splits
            ]
    else:
        # split the text into chunks
        refs = [
            {
                "title": (
                    doc_meta.name + (f", page {doc.end + 1}" if len(pages) > 1 else "")
                ),
                "url": add_page_number_to_pdf(
                    f_url, (doc.end + 1 if len(pages) > 1 else f_url)
                ).url,
                "snippet": doc.text,
                **doc.kwargs,
                "score": -1,
            }
            for doc in text_splitter(
                pages, chunk_size=chunk_size, chunk_overlap=chunk_overlap
            )
        ]
    return refs


def add_page_number_to_pdf(url: str | furl, page_num: int) -> furl:
    return furl(url).set(fragment_args={"page": page_num} if page_num else {})


sections_re = re.compile(r"(\s*[\r\n\f\v]|^)(\w+)\=", re.MULTILINE)


def split_sections(
    sections: str, *, chunk_overlap: int, chunk_size: int
) -> typing.Iterable[Document]:
    split = sections_re.split(sections)
    header = ""
    for i in range(2, len(split), 3):
        role = split[i].strip()
        content = split[i + 1].strip()
        if not content:
            continue
        match role:
            case "content" | "table":
                for doc in text_splitter(
                    content, chunk_size=chunk_size, chunk_overlap=chunk_overlap
                ):
                    doc.text = header + doc.text
                    yield doc

            case "csv":
                reader = csv.reader(io.StringIO(content))
                for prompt in table_arr_to_prompt_chunked(reader, chunk_size=1024):
                    yield Document(prompt, (0, 0))

            case _:
                header += f"{role}={content}\n"


@redis_cache_decorator
def doc_url_to_text_pages(
    *,
    f_url: str,
    doc_meta: DocMetadata,
    selected_asr_model: str | None,
) -> typing.Union[list[str], "pd.DataFrame"]:
    """
    Download document from url and convert to text pages.
    """
    f_bytes, mime_type = download_content_bytes(
        f_url=f_url, mime_type=doc_meta.mime_type
    )
    if not f_bytes:
        return []
    return any_bytes_to_text_pages_or_df(
        f_url=f_url,
        f_name=doc_meta.name,
        f_bytes=f_bytes,
        mime_type=mime_type,
        selected_asr_model=selected_asr_model,
    )


def download_content_bytes(*, f_url: str, mime_type: str) -> tuple[bytes, str]:
    if is_yt_url(f_url):
        return download_youtube_to_wav(f_url), "audio/wav"
    f = furl(f_url)
    if is_gdrive_url(f):
        # download from google drive
        return gdrive_download(f, mime_type)
    try:
        # download from url
        r = requests.get(
            f_url,
            headers={"User-Agent": random.choice(FAKE_USER_AGENTS)},
        )
        raise_for_status(r)
    except requests.RequestException as e:
        print(f"ignore error while downloading {f_url}: {e}")
        return b"", ""
    f_bytes = r.content
    # if it's a known encoding, standardize to utf-8
    encoding = r.apparent_encoding or r.encoding
    if encoding:
        try:
            codec = codecs.lookup(encoding)
        except LookupError:
            pass
        else:
            try:
                f_bytes = codec.decode(f_bytes)[0].encode()
            except UnicodeDecodeError:
                pass
    mime_type = get_mimetype_from_response(r)
    return f_bytes, mime_type


def any_bytes_to_text_pages_or_df(
    *,
    f_url: str,
    f_name: str,
    f_bytes: bytes,
    mime_type: str,
    selected_asr_model: str | None,
) -> typing.Union[list[str], "pd.DataFrame"]:
    if mime_type.startswith("audio/") or mime_type.startswith("video/"):
        if is_gdrive_url(furl(f_url)) or is_yt_url(f_url):
            f_url = upload_file_from_bytes(f_name, f_bytes, content_type=mime_type)
        transcript = run_asr(
            f_url,
            selected_model=(selected_asr_model or AsrModels.whisper_large_v2.name),
        )
        return [transcript]

    try:
        return pdf_or_tabular_bytes_to_text_pages_or_df(
            f_url=f_url,
            f_name=f_name,
            f_bytes=f_bytes,
            mime_type=mime_type,
            # for now, only use form recognizer if asr model is selected.
            # We should later change the doc extract settings to include the form recognizer option
            use_form_reco=bool(selected_asr_model),
        )
    except UnsupportedDocumentError:
        pass

    if mime_type == "text/plain":
        text = f_bytes.decode()
    else:
        ext = mimetypes.guess_extension(mime_type) or ""
        text = pandoc_to_text(f_name + ext, f_bytes)
    return [text]


def pdf_or_tabular_bytes_to_text_pages_or_df(
    *,
    f_url: str,
    f_name: str,
    f_bytes: bytes,
    mime_type: str,
    use_form_reco: bool,
):
    import pandas as pd

    if mime_type == "application/pdf":
        if use_form_reco:
            df = pdf_to_form_reco_df(f_url, f_name, f_bytes, mime_type)
        else:
            return pdf_to_text_pages(f=io.BytesIO(f_bytes))
    else:
        df = tabular_bytes_to_str_df(
            f_name=f_name, f_bytes=f_bytes, mime_type=mime_type
        )

    if "sections" in df.columns or "snippet" in df.columns:
        return df
    else:
        df.columns = [THEAD + col + THEAD for col in df.columns]
        return pd.DataFrame(["csv=" + df.to_csv(index=False)], columns=["sections"])


def is_yt_url(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


def tabular_bytes_to_str_df(
    *,
    f_name: str,
    f_bytes: bytes,
    mime_type: str,
) -> "pd.DataFrame":
    df = tabular_bytes_to_any_df(
        f_name=f_name, f_bytes=f_bytes, mime_type=mime_type, dtype=str
    )
    return df.fillna("")


def tabular_bytes_to_any_df(
    *,
    f_name: str,
    f_bytes: bytes,
    mime_type: str,
    dtype=None,
):
    import pandas as pd

    f = io.BytesIO(f_bytes)
    match mime_type:
        case "text/csv":
            df = pd.read_csv(f, dtype=dtype)
        case "text/tab-separated-values":
            df = pd.read_csv(f, sep="\t", dtype=dtype)
        case "application/json":
            df = pd.read_json(f, dtype=dtype)
        case "application/xml":
            df = pd.read_xml(f, dtype=dtype)
        case _ if "excel" in mime_type or "spreadsheet" in mime_type:
            df = pd.read_excel(f, dtype=dtype)
        case _:
            raise UnsupportedDocumentError(
                f"Unsupported document {mime_type=} ({f_name})"
            )
    return df


class UnsupportedDocumentError(UserError):
    pass


def pdf_to_text_pages(f: typing.BinaryIO) -> list[str]:
    import pdftotext

    return list(pdftotext.PDF(f))


def pdf_to_form_reco_df(
    f_url: str,
    f_name: str,
    f_bytes: bytes,
    mime_type: str,
) -> "pd.DataFrame":
    import pandas as pd

    if is_gdrive_url(furl(f_url)):
        f_url = upload_file_from_bytes(f_name, f_bytes, content_type=mime_type)
    num_pages = get_pdf_num_pages(f_bytes)
    return pd.DataFrame(
        map_parallel(
            lambda page_num: (
                add_page_number_to_pdf(f_url, page_num).url,
                f"{f_name}, page {page_num}",
                azure_doc_extract_page_num(f_url, page_num),
            ),
            range(1, num_pages + 1),
            max_workers=4,
        ),
        columns=["url", "title", "sections"],
    )


def get_pdf_num_pages(f_bytes: bytes) -> int:
    with tempfile.NamedTemporaryFile() as infile:
        infile.write(f_bytes)
        output = call_cmd("pdfinfo", infile.name).lower()
        for line in output.splitlines():
            if not line.startswith("pages:"):
                continue
            try:
                return int(line.split("pages:")[-1])
            except ValueError:
                raise ValueError(f"Unexpected PDF Info: {line}")


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
        call_cmd(
            "pandoc", "--standalone", infile.name, "--to", to, "--output", outfile.name
        )
        return outfile.read()


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
