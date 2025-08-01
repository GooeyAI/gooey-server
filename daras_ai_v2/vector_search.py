import codecs
import csv
import datetime
import hashlib
import io
import json
import mimetypes
import multiprocessing
import re
import tempfile
import typing
import unicodedata
from functools import partial
from time import time

import gooey_gui as gui
import numpy as np
import requests
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from furl import furl
from loguru import logger
from pydantic import BaseModel, Field

from app_users.models import AppUser
from celeryapp.tasks import get_running_saved_run
from daras_ai.image_input import (
    get_mimetype_from_response,
    safe_filename,
    upload_file_from_bytes,
)
from daras_ai_v2 import gcs_v2, settings
from daras_ai_v2.asr import (
    AsrModels,
    download_youtube_to_wav,
    run_asr,
    run_google_translate,
)
from daras_ai_v2.azure_doc_extract import (
    THEAD,
    azure_doc_extract_page_num,
    table_arr_to_prompt_chunked,
)
from daras_ai_v2.doc_search_settings_widgets import (
    is_user_uploaded_url,
)
from daras_ai_v2.embedding_model import EmbeddingModels, create_embeddings_cached
from daras_ai_v2.exceptions import UserError, call_cmd, raise_for_status
from daras_ai_v2.functional import (
    apply_parallel,
    flatmap_parallel_ascompleted,
    map_parallel,
)
from daras_ai_v2.gdrive_downloader import (
    gdrive_download,
    gdrive_metadata,
    is_gdrive_presentation_url,
    is_gdrive_url,
    url_to_gdrive_file_id,
)
from daras_ai_v2.office_utils_pptx import pptx_to_text_pages
from daras_ai_v2.onedrive_downloader import (
    is_onedrive_url,
    onedrive_meta,
    onedrive_download,
)
from daras_ai_v2.redis_cache import redis_lock
from daras_ai_v2.scraping_proxy import (
    SCRAPING_PROXIES,
    get_scraping_proxy_cert_path,
    requests_scraping_kwargs,
)
from daras_ai_v2.search_ref import (
    SearchReference,
    generate_text_fragment_url,
    remove_quotes,
)
from daras_ai_v2.text_splitter import Document, text_splitter
from embeddings.models import EmbeddedFile, EmbeddingsReference
from files.models import FileMetadata


if typing.TYPE_CHECKING:
    import pandas as pd


class DocSearchRequest(BaseModel):
    search_query: str
    keyword_query: str | list[str] | None = None

    documents: list[str] | None = None

    max_references: int | None = None
    max_context_words: int | None = None
    scroll_jump: int | None = None

    doc_extract_url: str | None = None
    check_document_updates: bool | None = False

    embedding_model: typing.Literal[tuple(e.name for e in EmbeddingModels)] | None = (
        None
    )
    dense_weight: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        title="Dense Embeddings Weightage",
        description="""
Weightage for dense vs sparse embeddings. `0` for sparse, `1` for dense, `0.5` for equal weight.
Generally speaking, dense embeddings excel at understanding the context of the query, whereas sparse vectors excel at keyword matches.
        """,
    )


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


def get_top_k_references(
    request: DocSearchRequest,
    is_user_url: bool = True,
    current_user: AppUser | None = None,
) -> typing.Generator[str, None, list[SearchReference]]:
    """
    Get the top k documents that ref the search query

    Args:
        request: the document search request
        is_user_url: whether the url is user-uploaded
        current_user: the current user

    Returns:
        the top k documents
    """
    from recipes.BulkRunner import url_to_runs

    input_docs = request.documents or []
    if not input_docs:
        return []

    if request.doc_extract_url:
        page_cls, sr, pr = url_to_runs(request.doc_extract_url)
        selected_asr_model = sr.state.get("selected_asr_model")
        google_translate_target = sr.state.get("google_translate_target")
    else:
        selected_asr_model = google_translate_target = None

    embedding_model = EmbeddingModels.get(
        request.embedding_model,
        default=EmbeddingModels.get(
            EmbeddedFile._meta.get_field("embedding_model").default
        ),
    )

    embedded_files, args_to_create = yield from do_check_document_updates(
        input_docs=input_docs,
        max_context_words=request.max_context_words,
        scroll_jump=request.scroll_jump,
        google_translate_target=google_translate_target,
        selected_asr_model=selected_asr_model,
        embedding_model=embedding_model,
        check_document_updates=request.check_document_updates,
    )

    if args_to_create:
        embedded_files += yield from apply_parallel(
            lambda args: create_embedded_file(
                *args,
                max_context_words=request.max_context_words,
                scroll_jump=request.scroll_jump,
                google_translate_target=google_translate_target,
                selected_asr_model=selected_asr_model,
                embedding_model=embedding_model,
                is_user_url=is_user_url,
                current_user=current_user,
            ),
            args_to_create,
            max_workers=4,
            message="Creating knowledge embeddings...",
        )

    if not embedded_files:
        yield "No embeddings found - skipping search"
        return []

    yield "Searching knowledge base..."

    vespa_file_ids = [ref.vespa_file_id for ref in embedded_files]
    EmbeddedFile.objects.filter(id__in=[ref.id for ref in embedded_files]).update(
        query_count=F("query_count") + 1,
        last_query_at=timezone.now(),
    )
    # chunk_count = sum(len(ref.document_ids) for ref in embedding_refs)
    # logger.debug(f"Knowledge base has {len(file_ids)} documents ({chunk_count} chunks)")

    s = time()
    search_result = query_vespa(
        request.search_query,
        request.keyword_query,
        file_ids=vespa_file_ids,
        limit=request.max_references or 100,
        embedding_model=embedding_model,
        semantic_weight=(
            request.dense_weight if request.dense_weight is not None else 1.0
        ),
    )
    references = list(vespa_search_results_to_refs(search_result))
    logger.debug(f"Search returned {len(references)} references in {time() - s:.2f}s")

    # merge duplicate references
    uniques: dict[str, SearchReference] = {}
    for key, ref in references:
        try:
            existing = uniques[key]
        except KeyError:
            uniques[key] = ref
        else:
            existing["snippet"] += "\n\n...\n\n" + ref["snippet"]
            existing["score"] = (existing["score"] + ref["score"]) / 2
    return list(uniques.values())


def vespa_search_results_to_refs(
    search_result: dict,
) -> typing.Iterable[SearchReference]:
    for hit in search_result["root"].get("children", []):
        try:
            ref = EmbeddingsReference.objects.get(vespa_doc_id=hit["fields"]["id"])
            ref_key = ref.url
        except EmbeddingsReference.DoesNotExist:
            continue
        if "text/html" in ref.embedded_file.metadata.mime_type:
            # logger.debug(f"Generating fragments {ref['url']} as it is a HTML file")
            ref.url = generate_text_fragment_url(url=ref.url, text=ref.snippet)
        yield (
            ref_key,
            SearchReference(
                url=ref.url,
                title=ref.title,
                snippet=ref.snippet,
                score=hit["relevance"],
            ),
        )


def query_vespa(
    search_query: str,
    keyword_query: str | list[str] | None,
    file_ids: list[str],
    limit: int,
    embedding_model: EmbeddingModels,
    semantic_weight: float = 1.0,
    threshold: float = 0.7,
    rerank_count: int = 1000,
) -> dict:
    if not file_ids:
        return {"root": {"children": []}}

    yql = "select * from %(schema)s where file_id in (@fileIds) and " % dict(
        schema=settings.VESPA_SCHEMA
    )
    bm25_yql = "( {targetHits: %(hits)i} userInput(@bm25Query) )"
    semantic_yql = "( {targetHits: %(hits)i, distanceThreshold: %(threshold)f} nearestNeighbor(embedding, queryEmbedding) )"

    if semantic_weight == 0.0:
        yql += bm25_yql % dict(hits=limit)
        ranking = "bm25"
    elif semantic_weight == 1.0:
        yql += semantic_yql % dict(hits=limit, threshold=threshold)
        ranking = "semantic"
    else:
        yql += (
            "( "
            + bm25_yql % dict(hits=rerank_count)
            + " or "
            + semantic_yql % dict(hits=rerank_count, threshold=threshold)
            + " )"
        )
        ranking = "fusion"

    body = {"yql": yql, "ranking": ranking, "hits": limit}

    if ranking in ("bm25", "fusion"):
        if isinstance(keyword_query, list):
            keyword_query = " ".join(keyword_query)
        body["bm25Query"] = remove_control_characters(keyword_query or search_query)

    logger.debug(
        "vespa query " + " ".join(repr(f"{k}={v}") for k, v in body.items()) + " ..."
    )

    if ranking in ("semantic", "fusion"):
        query_embedding = create_embeddings_cached(
            [search_query], model=embedding_model
        )[0]
        if query_embedding is None:
            return {"root": {"children": []}}
        body["input.query(queryEmbedding)"] = padded_embedding(query_embedding)

    body["fileIds"] = ", ".join(map(repr, file_ids))

    response = get_vespa_app().query(body)
    assert response.is_successful()

    return response.get_json()


def get_vespa_app():
    from vespa.application import Vespa

    return Vespa(url=settings.VESPA_URL)


def doc_or_yt_url_to_file_metas(
    f_url: str,
) -> tuple[FileMetadata, list[tuple[str, FileMetadata]]]:
    if is_yt_dlp_able_url(f_url):
        data = yt_dlp_extract_info(f_url)
        if data.get("_type") == "playlist":
            file_meta = yt_info_to_playlist_metadata(data)
            return file_meta, [
                (entry["url"], yt_info_to_video_metadata(entry))
                for entry in yt_dlp_info_to_entries(data)
            ]
        else:
            file_meta = yt_info_to_video_metadata(data)
            return file_meta, [(f_url, file_meta)]
    elif ret := fn_url_to_file_metadata(f_url):
        return ret
    else:
        file_meta = doc_url_to_file_metadata(f_url)
        return file_meta, [(f_url, file_meta)]


def yt_info_to_playlist_metadata(data: dict) -> FileMetadata:
    etag = data.get("modified_date") or data.get("playlist_count")
    return FileMetadata(
        name=data.get("title", "YouTube Playlist"),
        # youtube doesn't provide etag, so we use modified_date / playlist_count
        etag=etag and str(etag) or None,
        # will be converted later & saved as wav
        mime_type="audio/wav",
    )


def yt_info_to_video_metadata(data: dict) -> FileMetadata:
    etag = data.get("filesize_approx") or data.get("upload_date")
    return FileMetadata(
        name=data.get("title", "YouTube Video"),
        # youtube doesn't provide etag, so we use filesize_approx or upload_date
        etag=etag and str(etag) or None,
        # we will later convert & save as wav
        mime_type="audio/wav",
        total_bytes=data.get("filesize_approx", 0),
    )


def fn_url_to_file_metadata(
    leaf_url: str,
) -> tuple[FileMetadata, list[tuple[str, FileMetadata]]] | None:
    from functions.models import FunctionTrigger
    from functions.recipe_functions import WorkflowLLMTool
    from recipes.VideoBots import VideoBotsPage

    try:
        tool = WorkflowLLMTool(leaf_url)
    except Exception:
        return None
    if not tool.is_function_workflow:
        return None

    file_meta = FileMetadata(
        name=tool.fn_pr.title, etag=tool.fn_sr.created_at.isoformat()
    )

    sr = get_running_saved_run()
    tool.bind(
        saved_run=sr,
        workspace=sr.workspace,
        current_user=AppUser.objects.get(uid=sr.uid),
        request_model=VideoBotsPage.RequestModel,
        response_model=VideoBotsPage.ResponseModel,
        state=sr.state,
        trigger=FunctionTrigger.pre,
    )
    return_value = tool.call().get("return_value")
    if not isinstance(return_value, dict):
        return None
    documents = return_value.get("documents")
    if not isinstance(documents, list):
        documents = [documents]

    leaf_url_metas = []
    for doc in documents:
        leaf_meta = None
        match doc:
            case str():
                leaf_url = doc
            case dict():
                doc = doc.copy()
                try:
                    leaf_url = doc.pop("content", None)
                except KeyError:
                    continue
                leaf_meta = doc_url_to_file_metadata(leaf_url)
                if name := doc.pop("name", None):
                    leaf_meta.name = name
                if etag := doc.pop("etag", None):
                    leaf_meta.etag = etag
                if mime_type := doc.pop("mime_type", None):
                    leaf_meta.mime_type = mime_type
                leaf_meta.ref_data = doc
            case _:
                continue
        leaf_url_metas.append(
            (leaf_url, leaf_meta or doc_url_to_file_metadata(leaf_url))
        )

    return file_meta, leaf_url_metas


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
                    # language=HTML
                    f"""\
<p>This knowledge base Google Doc is not accessible: <a href="{f_url}" target="_blank">{f_url}</a></p>
<p>To address this:</p>
<ul>
    <li>Please make sure this Google Doc exists and is publicly viewable, or</li>
    <li>
    Share the Doc or its parent folder with <a href="mailto:support@gooey.ai" target="_blank">support@gooey.ai</a> as an authorized viewer and drop us an email.
    </li>
</ul>
                    """
                ) from e
            else:
                raise
        name = meta["name"]
        etag = meta.get("md5Checksum") or meta.get("modifiedTime")
        mime_type = meta["mimeType"]
        total_bytes = int(meta.get("size") or 0)
        export_links = meta.get("exportLinks", None)

    elif is_onedrive_url(f):
        meta = onedrive_meta(f_url, get_running_saved_run())
        name = meta["name"]
        etag = meta.get("eTag") or meta.get("lastModifiedDateTime")
        mime_type = meta["file"]["mimeType"]
        total_bytes = int(meta.get("size") or 0)
        export_links = {mime_type: meta["@microsoft.graph.downloadUrl"]}

    else:
        if is_user_uploaded_url(f_url):
            kwargs = {}
        elif f_url.startswith(gcs_v2.GCS_BUCKET_URL):
            f_url = gcs_v2.private_to_signed_url(f_url)
            kwargs = {}
        else:
            kwargs = requests_scraping_kwargs() | dict(
                timeout=settings.EXTERNAL_REQUEST_TIMEOUT_SEC
            )
        try:
            r = requests.head(f_url, **kwargs)
            if r.status_code == 405:
                r = requests.get(f_url, **kwargs, stream=True)
                r.close()
            raise_for_status(r)
        except requests.RequestException as e:
            logger.warning(f"ignore error while downloading {f_url}: {e}")
            name = None
            mime_type = None
            etag = None
            total_bytes = 0
            export_links = None
        else:
            name = (
                r.headers.get("content-disposition", "")
                .split("filename=")[-1]
                .strip('"')
            )
            etag = r.headers.get("etag", r.headers.get("last-modified"))
            if etag:
                etag = etag.strip('"')
            mime_type = get_mimetype_from_response(r)
            total_bytes = int(r.headers.get("content-length") or 0)
            export_links = None
    # extract filename from url as a fallback
    if not name:
        if is_user_uploaded_url(f_url):
            name = f.path.segments[-1]
        else:
            name = f"{f.host}{f.path}"
    # guess mimetype from name as a fallback
    if not mime_type:
        mime_type = mimetypes.guess_type(name)[0]

    file_metadata = FileMetadata(
        name=name, etag=etag, mime_type=mime_type or "", total_bytes=total_bytes
    )
    file_metadata.export_links = export_links or {}
    return file_metadata


def yt_dlp_info_to_entries(data: dict) -> list[dict]:
    entries = data.pop("entries", [data])
    return [e for e in entries if e]


def yt_dlp_extract_info(url: str, **params) -> dict:
    import yt_dlp

    # https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/options.py
    params = (
        dict(
            ignoreerrors=True,
            check_formats=False,
            extract_flat="in_playlist",
            proxy=SCRAPING_PROXIES.get("https"),
            client_certificate=get_scraping_proxy_cert_path(),
        )
        | params
    )
    with yt_dlp.YoutubeDL(params) as ydl:
        data = ydl.extract_info(url, download=False)
        if not data:
            raise UserError(
                f"Could not download the youtube video at {url!r}. "
                f"Please make sure the video is public and the url is correct."
            )
        return data


def do_check_document_updates(
    *,
    input_docs: list[str],
    max_context_words: int,
    scroll_jump: int,
    google_translate_target: str | None,
    selected_asr_model: str | None,
    embedding_model: EmbeddingModels,
    check_document_updates: bool,
) -> typing.Generator[
    str,
    None,
    tuple[
        list[EmbeddedFile],
        list[tuple[dict, FileMetadata, list[tuple[str, FileMetadata]]]],
    ],
]:
    if not input_docs:
        return [], []

    lookups = {}
    q = Q()
    for f_url in input_docs:
        lookup = dict(
            url=f_url,
            max_context_words=max_context_words,
            scroll_jump=scroll_jump,
            google_translate_target=google_translate_target or "",
            selected_asr_model=selected_asr_model or "",
            embedding_model=embedding_model.name,
        )
        q |= Q(**lookup)
        lookups[f_url] = lookup

    cached_files = {
        f.url: f
        for f in (
            EmbeddedFile.objects.filter(q)
            .select_related("metadata")
            .order_by("url", "-updated_at")
            .distinct("url")
        )
    }

    for f_url in cached_files:
        if is_user_uploaded_url(f_url) or not check_document_updates:
            lookups.pop(f_url, None)

    metadatas = yield from apply_parallel(
        doc_or_yt_url_to_file_metas,
        lookups.keys(),
        message="Fetching latest knowledge docs...",
        max_workers=100,
    )

    args_to_create = []
    for (f_url, lookup), (file_meta, leaf_url_metas) in zip(lookups.items(), metadatas):
        f = cached_files.get(f_url)
        if f and f.metadata == file_meta:
            continue
        else:
            args_to_create.append((lookup, file_meta, leaf_url_metas))

    return list(cached_files.values()), args_to_create


def create_embedded_file(
    lookup: dict,
    file_meta: FileMetadata,
    leaf_url_metas: list[tuple[str, FileMetadata]],
    *,
    max_context_words: int,
    scroll_jump: int,
    google_translate_target: str | None,
    selected_asr_model: str | None,
    embedding_model: EmbeddingModels,
    is_user_url: bool,
    current_user: AppUser,
) -> EmbeddedFile:
    """
    Return Vespa document ids and document tags
    for a given document url + metadata.
    """
    lock_id = _sha256(lookup)
    with redis_lock(f"gooey/get_or_create_embeddings/v1/{lock_id}"):
        # check if embeddings already exist and are up-to-date
        f = (
            EmbeddedFile.objects.filter(**lookup)
            .select_related("metadata")
            .order_by("-updated_at")
            .first()
        )
        if f and f.metadata == file_meta:
            return f

        # create fresh embeddings
        file_id = _sha256(lookup | dict(metadata=file_meta.astuple()))
        refs = []
        for leaf_url, leaf_meta in leaf_url_metas:
            refs += create_embeddings_in_search_db(
                f_url=leaf_url,
                file_meta=leaf_meta,
                file_id=file_id,
                max_context_words=max_context_words,
                scroll_jump=scroll_jump,
                google_translate_target=google_translate_target or "",
                selected_asr_model=selected_asr_model or "",
                embedding_model=embedding_model,
                is_user_url=is_user_url,
            )
        with transaction.atomic():
            EmbeddedFile.objects.filter(Q(**lookup) | Q(vespa_file_id=file_id)).delete()
            file_meta.save()
            embedded_file = EmbeddedFile.objects.create(
                vespa_file_id=file_id,
                metadata=file_meta,
                created_by=current_user,
                **lookup,
            )
            logger.debug(f"created: {embedded_file}")
            for ref in refs:
                ref.embedded_file = embedded_file
            EmbeddingsReference.objects.bulk_create(
                refs,
                update_conflicts=True,
                update_fields=["url", "title", "snippet", "updated_at"],
                unique_fields=["vespa_doc_id"],
            )
    return embedded_file


def create_embeddings_in_search_db(
    *,
    f_url: str,
    file_meta: FileMetadata,
    file_id: str,
    max_context_words: int,
    scroll_jump: int,
    google_translate_target: str | None,
    selected_asr_model: str | None,
    embedding_model: EmbeddingModels,
    is_user_url: bool,
) -> list[EmbeddingsReference]:
    refs = {}
    vespa = get_vespa_app()
    for ref, embedding in get_embeds_for_doc(
        f_url=f_url,
        file_meta=file_meta,
        max_context_words=max_context_words,
        scroll_jump=scroll_jump,
        google_translate_target=google_translate_target,
        selected_asr_model=selected_asr_model,
        embedding_model=embedding_model,
        is_user_url=is_user_url,
    ):
        doc_id = file_id + "/" + _sha256(ref)
        db_ref = EmbeddingsReference(
            vespa_doc_id=doc_id,
            url=ref["url"],
            title=ref["title"],
            snippet=ref["snippet"],
        )
        refs[db_ref.vespa_doc_id] = db_ref
        vespa.feed_data_point(
            schema=settings.VESPA_SCHEMA,
            data_id=doc_id,
            fields=format_embedding_row(
                doc_id=doc_id,
                created_at=db_ref.created_at,
                file_id=file_id,
                ref=ref,
                embedding=embedding,
            ),
            operation_type="feed",
        )
    return list(refs.values())


def _sha256(x) -> str:
    return hashlib.sha256(str(x).encode()).hexdigest()


def format_embedding_row(
    doc_id: str,
    file_id: str,
    ref: SearchReference,
    embedding: np.ndarray,
    created_at: datetime.datetime,
):
    return dict(
        id=doc_id,
        file_id=file_id,
        embedding=padded_embedding(embedding),
        created_at=int(created_at.timestamp() * 1000),
        title=remove_control_characters(ref["title"]),
        snippet=remove_control_characters(ref["snippet"]),
    )


def get_embeds_for_doc(
    *,
    f_url: str,
    file_meta: FileMetadata,
    max_context_words: int,
    scroll_jump: int,
    google_translate_target: str | None,
    selected_asr_model: str | None,
    embedding_model: EmbeddingModels,
    is_user_url: bool,
) -> typing.Iterator[tuple[SearchReference, np.ndarray]]:
    """
    Get document embeddings for a given document url.

    Args:
        f_url: document url
        file_meta: document metadata
        max_context_words: max number of words to include in each chunk
        scroll_jump: number of words to scroll by
        embedding_model: selected embedding model
        google_translate_target: target language for google translate
        selected_asr_model: selected ASR model (used for audio files)
        is_user_url: whether the url is user-uploaded

    Returns:
        list of (metadata, embeddings) tuples
    """
    pages = doc_url_to_text_pages(
        f_url=f_url,
        file_meta=file_meta,
        selected_asr_model=selected_asr_model,
        is_user_url=is_user_url,
    )
    refs = pages_to_split_refs(
        pages=pages,
        f_url=f_url,
        file_meta=file_meta,
        max_context_words=max_context_words,
        scroll_jump=scroll_jump,
    )
    translate_split_refs(refs, google_translate_target)
    texts = [m["title"] + " | " + m["snippet"] for m in refs]
    # get doc embeds in batches
    batch_size = 16  # azure openai limits
    return flatmap_parallel_ascompleted(
        partial(create_embeddings_cached, model=embedding_model),
        [refs[i : i + batch_size] for i in range(0, len(refs), batch_size)],
        [texts[i : i + batch_size] for i in range(0, len(texts), batch_size)],
        max_workers=2,
    )


def translate_split_refs(
    refs: list[SearchReference], google_translate_target: str | None
):
    if not google_translate_target:
        return
    snippets = [ref["snippet"] for ref in refs]
    translated_snippets = run_google_translate(snippets, google_translate_target)
    for ref, translated_snippet in zip(refs, translated_snippets):
        ref["snippet"] = translated_snippet


def pages_to_split_refs(
    *,
    pages,
    f_url: str,
    file_meta: FileMetadata,
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
                    "title": file_meta.name,
                    "url": f_url,
                    **row,  # preserve extra csv rows
                    "snippet": doc.text,
                    "score": -1,
                }
                for doc in splits
            ]
    else:
        # split the text into chunks
        refs = [
            {
                "title": (
                    file_meta.name + (f", page {doc.end + 1}" if len(pages) > 1 else "")
                ),
                "url": add_page_number_to_pdf(
                    f_url, (doc.end + 1 if len(pages) > 1 else None)
                ).url,
                **(file_meta.ref_data or {}),
                "snippet": doc.text,
                "score": -1,
            }
            for doc in text_splitter(
                pages, chunk_size=chunk_size, chunk_overlap=chunk_overlap
            )
        ]
    return refs


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


def doc_url_to_text_pages(
    *,
    f_url: str,
    file_meta: FileMetadata,
    selected_asr_model: str | None,
    is_user_url: bool = True,
) -> typing.Union[list[str], "pd.DataFrame"]:
    """
    Download document from url and convert to text pages.
    """
    f_bytes, mime_type = download_content_bytes(
        f_url=f_url,
        mime_type=file_meta.mime_type,
        is_user_url=is_user_url,
        export_links=file_meta.export_links,
    )
    if not f_bytes:
        return []
    return any_bytes_to_text_pages_or_df(
        f_url=f_url,
        f_name=file_meta.name,
        f_bytes=f_bytes,
        mime_type=mime_type,
        selected_asr_model=selected_asr_model,
    )


def download_content_bytes(
    *,
    f_url: str,
    mime_type: str,
    is_user_url: bool = True,
    export_links: dict[str, str] | None = None,
) -> tuple[bytes, str]:
    if export_links is None:
        export_links = {}
    if is_yt_dlp_able_url(f_url):
        return download_youtube_to_wav(f_url), "audio/wav"
    f = furl(f_url)
    if is_gdrive_url(f):
        return gdrive_download(f, mime_type, export_links)
    elif is_onedrive_url(f):
        return onedrive_download(mime_type, export_links)
    try:
        # download from url
        if is_user_uploaded_url(f_url):
            kwargs = {}
        elif f_url.startswith(gcs_v2.GCS_BUCKET_URL):
            f_url = gcs_v2.private_to_signed_url(f_url)
            kwargs = {}
        else:
            kwargs = requests_scraping_kwargs()
        r = requests.get(f_url, **kwargs)
        raise_for_status(r, is_user_url=is_user_url)
    except requests.RequestException as e:
        logger.warning(f"ignore error while downloading {f_url}: {e}")
        return b"", ""
    f_bytes = r.content
    # if it's a known encoding, standardize to utf-8
    encoding = r.headers.get("content-type", "").split("charset=")[-1].strip('"')
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
        if is_gdrive_url(furl(f_url)) or is_yt_dlp_able_url(f_url):
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

    match mime_type:
        case "text/plain" | "text/markdown":
            text = f_bytes.decode()
        case "application/json":
            try:
                text = json.dumps(json.loads(f_bytes.decode()), indent=2)
            except json.JSONDecodeError as e:
                raise UserError(f"Invalid JSON file: {e}") from e
        case _:
            ext = mimetypes.guess_extension(mime_type) or ""
            text = pandoc_to_text(f_name + ext, f_bytes)

    return [text]


def is_yt_dlp_able_url(url: str) -> bool:
    f = furl(url)
    return (
        "youtube.com" in f.origin
        or "youtu.be" in f.origin
        or "fb.watch" in f.origin
        or (
            ("facebook.com" in f.origin or "fb.com" in f.origin)
            and (
                "videos" in f.path.segments
                or "/share/v/" in f.pathstr
                or "v" in f.query.params
            )
        )
    )


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

    elif (
        mime_type
        == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ):
        return pptx_to_text_pages(f=io.BytesIO(f_bytes))

    else:
        df = tabular_bytes_to_str_df(
            f_name=f_name, f_bytes=f_bytes, mime_type=mime_type
        )

    if "sections" in df.columns or "snippet" in df.columns:
        return df
    else:
        df.columns = [THEAD + str(col) + THEAD for col in df.columns]
        return pd.DataFrame(["csv=" + df.to_csv(index=False)], columns=["sections"])


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
        case _ if "excel" in mime_type or "sheet" in mime_type:
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


def add_page_number_to_pdf(url: str | furl, page_num: int) -> furl:
    if is_gdrive_presentation_url(furl(url)):
        param = "slide"
    else:
        param = "page"
    return furl(url).set(fragment_args={param: page_num} if page_num else {})


# dont use more than 1GB of memory for pandoc in total
MAX_PANDOC_MEM_MB = 512
_pandoc_lock = multiprocessing.Semaphore(4)  # semaphore ensures max pandoc processes


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
        _pandoc_lock,
        tempfile.NamedTemporaryFile("wb", suffix="." + safe_filename(f_name)) as infile,
        tempfile.NamedTemporaryFile("r") as outfile,
    ):
        infile.write(f_bytes)
        call_cmd(
            "pandoc",
            # https://pandoc.org/MANUAL.html#a-note-on-security
            "+RTS", f"-M{MAX_PANDOC_MEM_MB}M", "-RTS", "--sandbox",
            "--standalone",
            infile.name,
            "--wrap", "none",
            "--to", to,
            "--output",
            outfile.name,
        )  # fmt: skip
        return outfile.read()


def render_sources_widget(refs: list[SearchReference]):
    if not refs:
        return
    with gui.expander("💁‍♀️ Sources"):
        for idx, ref in enumerate(refs):
            gui.html(
                # language=HTML
                f"""<p>{idx + 1}. <a href="{ref["url"]}" target="_blank">{ref["title"]}</a></p>""",
            )
            gui.text(ref["snippet"], style={"maxHeight": "200px"})
        gui.write(
            "---\n"
            + "```text\n"
            + "\n".join(f"[{idx + 1}] {ref['url']}" for idx, ref in enumerate(refs))
            + "\n```",
            disabled=True,
        )


def remove_control_characters(s):
    # from https://docs.vespa.ai/en/troubleshooting-encoding.html
    return "".join(ch for ch in s if unicodedata.category(ch)[0] != "C")


EMBEDDING_SIZE = 3072


def padded_embedding(
    arr: np.ndarray, max_len: int = EMBEDDING_SIZE, pad_value: float = 0.0
) -> list:
    return [pad_value] * (max_len - len(arr)) + arr.tolist()
