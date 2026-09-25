import hashlib
import io
import mimetypes
import typing
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from functools import partial

import numpy as np
from aifail import (
    http_should_retry,
    retry_if,
    try_all,
)
from furl import furl
from jinja2.lexer import whitespace_re
from loguru import logger

from daras_ai.image_input import gs_url_to_uri
from daras_ai_v2 import settings
from daras_ai_v2.asr import get_google_auth_session
from daras_ai_v2.exceptions import UserError, raise_for_status
from daras_ai_v2.gpu_server import call_celery_task
from daras_ai_v2.language_model import get_openai_client, openai_should_retry
from daras_ai_v2.redis_cache import (
    get_redis_cache,
)


class EmbeddingModel(typing.NamedTuple):
    model_id: typing.Iterable[str] | str
    label: str

    # Per-model capabilities. These live in code, so adding or correcting a model still
    # needs a deploy -- the ai_models.AIModelSpec table is where they want to end up.
    supports_multimodal: bool = False
    max_images: int = 0
    max_audio_seconds: int = 0
    max_video_seconds: int = 0
    max_documents: int = 0
    max_document_pages: int = 0


class EmbeddingInput(typing.NamedTuple):
    """One thing to embed: either a text snippet or an uploaded media file."""

    text: str | None = None
    url: str | None = None


class EmbeddingModels(Enum):
    openai_3_large = EmbeddingModel(
        model_id=("openai-text-embedding-3-large-prod-ca-1", "text-embedding-3-large"),
        label="Text Embedding 3 Large (OpenAI)",
    )
    openai_3_small = EmbeddingModel(
        model_id=("openai-text-embedding-3-small-prod-ca-1", "text-embedding-3-small"),
        label="Text Embedding 3 Small (OpenAI)",
    )
    openai_ada_2 = EmbeddingModel(
        model_id=("openai-text-embedding-ada-002-prod-ca-1", "text-embedding-ada-002"),
        label="Text Embedding Ada 2 (OpenAI)",
    )

    gemini_embedding_2 = EmbeddingModel(
        model_id="gemini-embedding-2",
        label="Gemini Embedding 2 (Google)",
        # text, images, audio, video and PDFs all land in one shared vector space,
        # so media can be retrieved by a plain text query
        supports_multimodal=True,
        max_images=6,
        max_audio_seconds=180,
        max_video_seconds=120,
        max_documents=1,
        max_document_pages=6,
    )

    mistral_embed = EmbeddingModel(
        model_id="mistral-embed",
        label="Mistral Embed (Mistral AI)",
    )

    e5_large_v2 = EmbeddingModel(
        model_id="intfloat/e5-large-v2",
        label="E5 large v2 (Liang Wang)",
    )
    e5_base_v2 = EmbeddingModel(
        model_id="intfloat/e5-base-v2",
        label="E5 base v2 (Liang Wang)",
    )
    multilingual_e5_base = EmbeddingModel(
        model_id="intfloat/multilingual-e5-base",
        label="Multilingual E5 Base (Liang Wang)",
    )
    multilingual_e5_large = EmbeddingModel(
        model_id="intfloat/multilingual-e5-large",
        label="Multilingual E5 Large (Liang Wang)",
    )
    gte_large = EmbeddingModel(
        model_id="thenlper/gte-large",
        label="General Text Embeddings Large (Dingkun Long)",
    )
    gte_base = EmbeddingModel(
        model_id="thenlper/gte-base",
        label="General Text Embeddings Base (Dingkun Long)",
    )

    @property
    def model_id(self) -> typing.Iterable[str] | str:
        return self.value.model_id

    @property
    def label(self) -> str:
        return self.value.label

    @property
    def supports_multimodal(self) -> bool:
        return self.value.supports_multimodal

    @property
    def max_images(self) -> int:
        return self.value.max_images

    @property
    def max_audio_seconds(self) -> int:
        return self.value.max_audio_seconds

    @property
    def max_video_seconds(self) -> int:
        return self.value.max_video_seconds

    @property
    def max_documents(self) -> int:
        return self.value.max_documents

    @property
    def max_document_pages(self) -> int:
        return self.value.max_document_pages

    @classmethod
    def get(cls, key, default=None):
        try:
            return cls[key]
        except KeyError:
            return default


def create_embeddings_cached(
    texts: list[str], model: EmbeddingModels
) -> list[np.ndarray | None]:
    # replace newlines, which can negatively affect performance.
    texts = [whitespace_re.sub(" ", text) for text in texts]
    # get the redis cache
    redis_cache = get_redis_cache()
    # load the embeddings from the cache
    ret = [
        (
            np_loads(data)
            if (data := redis_cache.get(_embed_cache_key(text, model.name)))
            else None
        )
        for text in texts
    ]
    # list of embeddings that need to be created
    misses = [i for i, c in enumerate(ret) if c is None]
    if misses:
        # create the embeddings in bulk
        embeddings = create_embeddings(texts=[texts[i] for i in misses], model=model)
        for i, embedding in zip(misses, embeddings):
            # save the embedding to the cache
            text = texts[i]
            redis_cache.set(_embed_cache_key(text, model.name), np_dumps(embedding))
            # fill in missing values
            ret[i] = embedding
    return ret


def create_embeddings(texts: list[str], model: EmbeddingModels) -> np.ndarray:
    if "openai" in model.name:
        ret = _run_openai_embedding(texts=texts, model_id=model.model_id)
    elif "mistral" in model.name:
        ret = _run_openai_embedding(
            texts=texts,
            model_id=model.model_id,
            base_url="https://api.mistral.ai/v1",
            api_key=settings.MISTRAL_API_KEY,
        )
    elif "gemini" in model.name:
        ret = _run_vertex_embedding(
            contents=[{"parts": [{"text": text}]} for text in texts],
            model_id=model.model_id,
        )
    else:
        ret = _run_gpu_embedding(texts=texts, model_id=model.model_id)

    return _validate_embeddings(ret, expected_len=len(texts))


def create_multimodal_embeddings(
    inputs: list[EmbeddingInput], model: EmbeddingModels
) -> np.ndarray:
    """
    Embed a mixed list of texts and media files, one vector per input.

    Every input becomes its own `content`, which is what yields an embedding each --
    bundling several parts into one `content` would instead return a single aggregated
    vector for the lot.
    """
    if not model.supports_multimodal:
        raise UserError(f"{model.label} cannot embed media, only text.")

    ret = _run_vertex_embedding(
        contents=[{"parts": [_embedding_input_to_part(inp)]} for inp in inputs],
        model_id=model.model_id,
    )
    return _validate_embeddings(ret, expected_len=len(inputs))


def _embedding_input_to_part(inp: EmbeddingInput) -> dict:
    if inp.url:
        return {
            "file_data": {
                "mime_type": mimetypes.guess_type(inp.url)[0]
                or "application/octet-stream",
                "file_uri": _user_media_url_to_gs_uri(inp.url),
            }
        }
    return {"text": inp.text or ""}


def _user_media_url_to_gs_uri(url: str) -> str:
    """
    Convert the url of a file uploaded to our own bucket into a gs:// uri for Vertex.

    Vertex fetches the file with our own service account, so the url has to be checked
    here: gs_url_to_uri alone throws away the host and turns whatever path it's given
    into a bucket name, which would let any caller make us read any object that account
    can see and hand back its embedding.
    """
    f = furl(url)
    segments = f.path.segments
    media_segments = furl(settings.GS_MEDIA_PATH).path.segments
    prefix = [settings.GS_BUCKET_NAME, *media_segments]
    if not (
        settings.GS_BUCKET_NAME
        and f.scheme == "https"
        and f.host == "storage.googleapis.com"
        and segments[: len(prefix)] == prefix
        # something must follow the prefix, and nothing may climb back out of it once
        # the segments are percent-decoded and rejoined into the uri
        and len(segments) > len(prefix)
        and not any(s in ("", ".", "..") or "/" in s for s in segments)
    ):
        raise UserError(
            f"Can't embed {url!r}: only files uploaded to Gooey can be embedded. "
            "Upload the file first (via the form, or the [Upload Files via Form Data] "
            "option on https://gooey.ai/api/) and pass the url you get back."
        )
    return gs_url_to_uri(url)


def _validate_embeddings(ret: list[list[float]], *, expected_len: int) -> np.ndarray:
    arr = np.array(ret)
    # see - https://community.openai.com/t/text-embedding-ada-002-embeddings-sometime-return-nan/279664/5
    if np.isnan(arr).any():
        raise RuntimeError("NaNs detected in embedding")
        # raise openai.error.APIError("NaNs detected in embedding")  # this lets us retry
    if arr.shape[0] != expected_len or arr.shape[1] < 128:
        raise RuntimeError(f"Unexpected shape for embedding: {arr.shape}")

    return arr


def _embed_cache_key(text: str, model_name: str) -> str:
    return f"gooey/{model_name}/v1/{sha256(text)}"


def sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def np_loads(data: bytes) -> np.ndarray:
    return np.load(io.BytesIO(data))


def np_dumps(a: np.ndarray) -> bytes:
    f = io.BytesIO()
    np.save(f, a)
    return f.getvalue()


def _run_gpu_embedding(texts: list[str], model_id: str) -> list[list[float]]:
    logger.info(f"{model_id=}, {len(texts)=}")
    return call_celery_task(
        "text_embeddings", pipeline={"model_id": model_id}, inputs={"texts": texts}
    )


@retry_if(openai_should_retry)
def _run_openai_embedding(
    *,
    texts: list[str],
    model_id: typing.Iterable[str] | str,
    base_url: str | None = None,
    api_key: str | None = None,
) -> list[list[float]]:
    logger.info(f"{model_id=}, {len(texts)=}")
    if isinstance(model_id, str):
        model_id = [model_id]
    res = try_all(
        *[
            partial(
                get_openai_client(
                    model_str, base_url=base_url, api_key=api_key
                ).embeddings.create,
                model=model_str,
                input=texts,
            )
            for model_str in model_id
        ],
    )
    return [data.embedding for data in res.data]


# gemini-embedding-2 emits 128..3072 dims (Matryoshka, auto-renormalized). 3072 is the max
# and exactly matches vector_search.EMBEDDING_SIZE, so it needs no zero padding to be fed
# into the Vespa `tensor<float>(x[3072])` field.
GEMINI_EMBEDDING_DIMENSIONS = 3072

# gemini-embedding-2 is only served from Vertex's multi-region "rep" endpoints, which take
# just "us" or "eu" -- not a specific region like the classic {region}-aiplatform.googleapis.com
# host this codebase uses elsewhere for Gemini chat/vision calls (see _call_gemini_api).
# There is also no batch call for this model, unlike the older text embedding models: every
# content needs its own :embedContent request, so we fan them out across a thread pool.
GEMINI_EMBEDDING_LOCATION = "us"
VERTEX_EMBEDDING_MAX_WORKERS = 10


def _run_vertex_embedding(*, contents: list[dict], model_id: str) -> list[list[float]]:
    logger.info(f"{model_id=}, {len(contents)=}")
    session, project = get_google_auth_session()
    # the model is addressed by its fully qualified resource path
    model_uri = (
        f"projects/{project}/locations/{GEMINI_EMBEDDING_LOCATION}"
        f"/publishers/google/models/{model_id}"
    )
    with ThreadPoolExecutor(max_workers=VERTEX_EMBEDDING_MAX_WORKERS) as pool:
        return list(
            pool.map(
                lambda content: _vertex_embed_content(
                    session=session, model_uri=model_uri, content=content
                ),
                contents,
            )
        )


@retry_if(http_should_retry)
def _vertex_embed_content(*, session, model_uri: str, content: dict) -> list[float]:
    r = session.post(
        f"https://aiplatform.{GEMINI_EMBEDDING_LOCATION}.rep.googleapis.com"
        f"/v1/{model_uri}:embedContent",
        json={
            "content": content,
            "embedContentConfig": {"outputDimensionality": GEMINI_EMBEDDING_DIMENSIONS},
        },
    )
    raise_for_status(r)
    return r.json()["embedding"]["values"]
