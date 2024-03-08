import codecs
import csv
import hashlib
import io
import mimetypes
import random
import re
import tempfile
import typing
import uuid
from functools import partial

import numpy as np
import requests
from furl import furl
from googleapiclient.errors import HttpError
from loguru import logger
from pydantic import BaseModel, Field
from rank_bm25 import BM25Okapi
from vespa.application import Vespa

import gooey_ui as gui
from daras_ai.image_input import (
    upload_file_from_bytes,
    safe_filename,
    guess_ext_from_response,
    get_mimetype_from_response,
)
from daras_ai_v2 import settings
from daras_ai_v2.asr import AsrModels, run_asr, run_google_translate
from daras_ai_v2.azure_doc_extract import (
    table_arr_to_prompt_chunked,
)
from daras_ai_v2.doc_search_settings_widgets import (
    is_user_uploaded_url,
)
from daras_ai_v2.exceptions import raise_for_status, call_cmd, UserError
from daras_ai_v2.fake_user_agents import FAKE_USER_AGENTS
from daras_ai_v2.functional import (
    flatmap_parallel,
    map_parallel,
    flatmap_parallel_ascompleted,
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
from bots.models import EmbeddingsReference


class DocSearchRequest(BaseModel):
    search_query: str
    keyword_query: str | list[str] | None

    documents: list[str] | None

    max_references: int | None
    max_context_words: int | None
    scroll_jump: int | None

    selected_asr_model: typing.Literal[tuple(e.name for e in AsrModels)] | None
    google_translate_target: str | None

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
    yield "Fetching latest knowledge docs..."
    input_docs = request.documents or []
    doc_metas = map_parallel(doc_url_to_metadata, input_docs)

    yield "Creating knowledge embeddings..."
    embedding_refs = map_parallel(
        partial(
            get_or_create_embeddings,
            max_context_words=request.max_context_words or 1000,
            scroll_jump=request.scroll_jump or 5,
        ),
        input_docs,
        doc_metas,
    )

    doc_tags = list([embedding_ref.doc_tag for embedding_ref in embedding_refs])
    chunk_count = sum(
        [len(embedding_ref.document_ids) for embedding_ref in embedding_refs]
    )
    yield f"Knowledge base has {len(doc_tags)} documents and {chunk_count} chunks"

    if doc_tags:
        yield "Searching knowledge base"
        search_results = query_vespa(
            request.search_query,
            doc_tags=doc_tags,
            limit=request.max_references or 100,
            semantic_weight=(
                request.dense_weight if request.dense_weight is not None else 1.0
            ),
        )
        result = search_results_to_refs(search_results)
        logger.info(f"Found {len(result)} relevant documents")
        yield f"Found {len(result)} relevant documents"
        return result
    else:
        yield "No documents found - skipping search"
        return []


def search_results_to_refs(search_result: dict) -> list[SearchReference]:
    return [
        SearchReference(
            url=hit["fields"]["url"],
            title=hit["fields"]["title"],
            snippet=hit["fields"]["snippet"],
            score=hit["relevance"],
        )
        for hit in search_result["root"].get("children", [])
    ]


def query_vespa(
    search_query: str, doc_tags: list[str], limit: int, semantic_weight: float = 1.0
) -> dict:
    query_embedding = openai_embedding_create([search_query])[0]
    assert query_embedding is not None
    vespa_doc_tags = ", ".join([f"'{tag}'" for tag in doc_tags])
    query = f"select * from {settings.VESPA_SCHEMA} where doc_tag in ({vespa_doc_tags}) and (userQuery() or ({{targetHits: {limit}}}nearestNeighbor(embedding, q))) limit {limit}"
    logger.info(f"Vespa query: {'-'*80}\n{query}\n{'-'*80}")
    if semantic_weight == 1.0:
        ranking = "semantic"
    elif semantic_weight == 0.0:
        ranking = "bm25"
    else:
        ranking = "fusion"
    response = get_vespa_app().query(
        yql=query,
        query=search_query,
        ranking=ranking,
        body={
            "ranking.features.query(q)": query_embedding.tolist(),
            "ranking.features.query(semanticWeight)": semantic_weight,
        },
    )
    assert response.is_successful()
    return response.get_json()


def get_vespa_app():
    return Vespa(url=settings.VESPA_URL)


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


def doc_url_to_metadata(f_url: str) -> DocMetadata:
    """
    Fetches the metadata for a document url

    Args:
        f_url: document url

    Returns:
        document metadata
    """
    return DocMetadata.from_file_metadata(doc_url_to_file_metadata(f_url))


def doc_url_to_file_metadata(f_url: str) -> FileMetadata:
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
        google_translate_target=google_translate_target,
    )
    refs = pages_to_split_refs(
        pages=pages,
        f_url=f_url,
        doc_meta=doc_meta,
        max_context_words=max_context_words,
        scroll_jump=scroll_jump,
    )
    tokenized_corpus = [
        bm25_tokenizer(ref["title"]) + bm25_tokenizer(ref["snippet"]) for ref in refs
    ]
    return tokenized_corpus


def get_embeds_for_doc(
    *,
    f_url: str,
    doc_meta: DocMetadata,
    max_context_words: int,
    scroll_jump: int,
    google_translate_target: str | None = None,
    selected_asr_model: str | None = None,
) -> typing.Iterator[tuple[SearchReference, np.ndarray]]:
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
    refs = pages_to_split_refs(
        pages=pages,
        f_url=f_url,
        doc_meta=doc_meta,
        max_context_words=max_context_words,
        scroll_jump=scroll_jump,
    )
    texts = [m["title"] + " | " + m["snippet"] for m in refs]
    # get doc embeds in batches
    batch_size = 16  # azure openai limits
    return flatmap_parallel_ascompleted(
        openai_embedding_create,
        [refs[i : i + batch_size] for i in range(0, len(refs), batch_size)],
        [texts[i : i + batch_size] for i in range(0, len(texts), batch_size)],
        max_workers=2,
    )


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
    google_translate_target: str | None,
    selected_asr_model: str | None,
) -> typing.Union[list[str], "pd.DataFrame"]:
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
    f_bytes, ext = download_content_bytes(f_url=f_url, mime_type=doc_meta.mime_type)
    if not f_bytes:
        return []
    pages = bytes_to_text_pages_or_df(
        f_url=f_url,
        f_name=doc_meta.name,
        f_bytes=f_bytes,
        ext=ext,
        mime_type=doc_meta.mime_type,
        selected_asr_model=selected_asr_model,
    )
    # optionally, translate text
    if google_translate_target and isinstance(pages, list):
        pages = run_google_translate(pages, google_translate_target)
    return pages


def download_content_bytes(*, f_url: str, mime_type: str) -> tuple[bytes, str]:
    f = furl(f_url)
    if is_gdrive_url(f):
        # download from google drive
        return gdrive_download(f, mime_type)
    try:
        # download from url
        r = requests.get(
            f_url,
            headers={"User-Agent": random.choice(FAKE_USER_AGENTS)},
            timeout=settings.EXTERNAL_REQUEST_TIMEOUT_SEC,
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
    ext = guess_ext_from_response(r)
    return f_bytes, ext


def bytes_to_text_pages_or_df(
    *,
    f_url: str,
    f_name: str,
    f_bytes: bytes,
    ext: str,
    mime_type: str,
    selected_asr_model: str | None,
) -> typing.Union[list[str], "pd.DataFrame"]:
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
            if is_gdrive_url(furl(f_url)):
                f_url = upload_file_from_bytes(f_name, f_bytes, content_type=mime_type)
            pages = [run_asr(f_url, selected_model=selected_asr_model, language="en")]
        case _:
            df = bytes_to_df(f_name=f_name, f_bytes=f_bytes, ext=ext)
            assert (
                "snippet" in df.columns or "sections" in df.columns
            ), f'uploaded spreadsheet must contain a "snippet" or "sections" column - {f_name !r}'
            return df

    return pages


def bytes_to_df(
    *,
    f_name: str,
    f_bytes: bytes,
    ext: str,
) -> "pd.DataFrame":
    import pandas as pd

    f = io.BytesIO(f_bytes)
    match ext:
        case ".csv":
            df = pd.read_csv(f, dtype=str)
        case ".tsv":
            df = pd.read_csv(f, sep="\t", dtype=str)
        case ".xls" | ".xlsx":
            df = pd.read_excel(f, dtype=str)
        case ".json":
            df = pd.read_json(f, dtype=str)
        case ".xml":
            df = pd.read_xml(f, dtype=str)
        case _:
            raise ValueError(f"Unsupported document format {ext!r} ({f_name})")
    return df.fillna("")


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


@redis_cache_decorator
def get_or_create_embeddings(
    f_url: str,
    doc_meta: DocMetadata,
    *,
    max_context_words: int,
    scroll_jump: int,
    google_translate_target: str | None = None,
    selected_asr_model: str | None = None,
) -> EmbeddingsReference:
    """
    Return Vespa document ids and document tags
    for a given document url + metadata.
    """
    uniqueness_args = {
        "f_url": f_url,
        "doc_meta": doc_meta,
        "max_context_words": max_context_words,
        "scroll_jump": scroll_jump,
        "google_translate_target": google_translate_target,
        "selected_asr_model": selected_asr_model,
    }
    doc_tag = hashlib.sha256(
        str({hash(k): hash(v) for k, v in uniqueness_args.items()}).encode("utf-8")
    ).hexdigest()

    try:
        embedding_ref = EmbeddingsReference.objects.get(
            url=f_url,
            doc_tag=doc_tag,
        )
    except EmbeddingsReference.DoesNotExist:
        document_ids = create_embeddings_in_search_db(
            f_url=f_url,
            doc_meta=doc_meta,
            doc_tag=doc_tag,
            max_context_words=max_context_words,
            scroll_jump=scroll_jump,
            google_translate_target=google_translate_target,
            selected_asr_model=selected_asr_model,
        )
        embedding_ref = EmbeddingsReference(
            url=f_url,
            doc_tag=doc_tag,
            document_ids=document_ids,
        )
        embedding_ref.full_clean()
        embedding_ref.save()

    return embedding_ref


def create_embeddings_in_search_db(
    *,
    f_url: str,
    doc_meta: DocMetadata,
    max_context_words: int,
    scroll_jump: int,
    doc_tag: str,
    google_translate_target: str | None = None,
    selected_asr_model: str | None = None,
):
    document_ids = []
    vespa = get_vespa_app()
    for ref, embedding in get_embeds_for_doc(
        f_url=f_url,
        doc_meta=doc_meta,
        max_context_words=max_context_words,
        scroll_jump=scroll_jump,
        google_translate_target=google_translate_target,
        selected_asr_model=selected_asr_model,
    ):
        document_id = str(uuid.uuid4())
        vespa.feed_data_point(
            schema=settings.VESPA_SCHEMA,
            data_id=document_id,
            fields=format_embedding_row(
                document_id,
                ref=ref,
                embedding=embedding,
                doc_tag=doc_tag,
            ),
            operation_type="feed",
        )
        document_ids.append(document_id)

    return document_ids


def format_embedding_row(
    id: str,
    ref: SearchReference,
    embedding: np.ndarray,
    doc_tag: str,
):
    return {
        "id": id,
        "url": ref["url"],
        "title": ref["title"],
        "snippet": ref["snippet"].replace("\f", ""),  # 0xC is illegal in Vespa
        "embedding": embedding.tolist(),
        "doc_tag": doc_tag,
    }
