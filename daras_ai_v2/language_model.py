import hashlib
import io
import re
import threading
import typing
from enum import Enum
from functools import wraps
from time import sleep

import numpy as np
import tiktoken
import typing_extensions
from jinja2.lexer import whitespace_re

from daras_ai_v2.redis_cache import (
    get_redis_cache,
)

_gpt2_tokenizer = None


DEFAULT_SYSTEM_MSG = "You are an intelligent AI assistant. Follow the instructions as closely as possible."

CHATML_START_TOKEN = "<|im_start|>"
CHATML_END_TOKEN = "<|im_end|>"

CHATML_ROLE_SYSTEM = "system"
CHATML_ROLE_ASSISSTANT = "assistant"
CHATML_ROLE_USER = "user"


class LargeLanguageModels(Enum):
    gpt_4 = "GPT-4"
    gpt_3_5_turbo = "ChatGPT (GPT-3.5-turbo)"
    gpt_3_5_turbo_16k = "ChatGPT+ (GPT-3.5-turbo-16k)"

    text_davinci_003 = "GPT-3.5 (Davinci-3)"
    text_davinci_002 = "GPT-3.5 (Davinci-2)"
    text_curie_001 = "Curie"
    text_babbage_001 = "Babbage"
    text_ada_001 = "Ada"
    code_davinci_002 = "Codex (Deprecated)"

    def is_chat_model(self) -> bool:
        return self in [
            LargeLanguageModels.gpt_4,
            LargeLanguageModels.gpt_3_5_turbo,
            LargeLanguageModels.gpt_3_5_turbo_16k,
        ]


engine_names = {
    LargeLanguageModels.gpt_4: "gpt-4",
    LargeLanguageModels.gpt_3_5_turbo: "gpt-3.5-turbo",
    LargeLanguageModels.gpt_3_5_turbo_16k: "gpt-3.5-turbo-16k",
    LargeLanguageModels.text_davinci_003: "text-davinci-003",
    LargeLanguageModels.text_davinci_002: "text-davinci-002",
    LargeLanguageModels.code_davinci_002: "code-davinci-002",
    LargeLanguageModels.text_curie_001: "text-curie-001",
    LargeLanguageModels.text_babbage_001: "text-babbage-001",
    LargeLanguageModels.text_ada_001: "text-ada-001",
}


model_max_tokens = {
    # https://platform.openai.com/docs/models/gpt-4
    LargeLanguageModels.gpt_4: 8192,
    # https://platform.openai.com/docs/models/gpt-3-5
    LargeLanguageModels.gpt_3_5_turbo: 4096,
    LargeLanguageModels.gpt_3_5_turbo_16k: 16_384,
    LargeLanguageModels.text_davinci_003: 4097,
    LargeLanguageModels.text_davinci_002: 4097,
    LargeLanguageModels.code_davinci_002: 8001,
    # https://platform.openai.com/docs/models/gpt-3
    LargeLanguageModels.text_curie_001: 2049,
    LargeLanguageModels.text_babbage_001: 2049,
    LargeLanguageModels.text_ada_001: 2049,
}


def calc_gpt_tokens(
    text: str | list[str] | dict | list[dict],
    *,
    sep: str = "",
    is_chat_model: bool = True,
) -> int:
    local = threading.local()
    try:
        enc = local.gpt2enc
    except AttributeError:
        enc = tiktoken.get_encoding("gpt2")
        local.gpt2enc = enc
    if isinstance(text, (str, dict)):
        messages = [text]
    else:
        messages = text
    combined = sep.join(
        content
        for entry in messages
        if (
            content := (
                format_chatml_message(entry) + "\n"
                if is_chat_model
                else entry.get("content", "")
            )
            if isinstance(entry, dict)
            else str(entry)
        )
    )
    return len(enc.encode(combined))


F = typing.TypeVar("F", bound=typing.Callable[..., typing.Any])


def get_openai_error_cls():
    import openai

    return (
        openai.error.Timeout,
        openai.error.APIError,
        openai.error.APIConnectionError,
        openai.error.RateLimitError,
        openai.error.ServiceUnavailableError,
    )


def do_retry(
    max_retries: int = 5,
    retry_delay: float = 5,
    get_error_cls=get_openai_error_cls,
) -> typing.Callable[[F], F]:
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            n = 0
            while True:
                try:
                    return fn(*args, **kwargs)
                except get_error_cls() as e:
                    if n < max_retries:
                        n += 1
                        print(
                            f"({n}/5) captured error, retry in {retry_delay}s:", repr(e)
                        )
                        sleep(retry_delay)
                    else:
                        raise

        return wrapper

    return decorator


def openai_embedding_create(texts: list[str]) -> list[np.ndarray]:
    # replace newlines, which can negatively affect performance.
    texts = [whitespace_re.sub(" ", text) for text in texts]
    # get the redis cache
    redis_cache = get_redis_cache()
    # load the embeddings from the cache
    ret = [
        np_loads(data) if (data := redis_cache.get(_embed_cache_key(text))) else None
        for text in texts
    ]
    # list of embeddings that need to be created
    misses = [i for i, c in enumerate(ret) if c is None]
    if misses:
        # create the embeddings in bulk
        embeddings = _openai_embedding_create(input=[texts[i] for i in misses])
        for i, embedding in zip(misses, embeddings):
            # save the embedding to the cache
            text = texts[i]
            redis_cache.set(_embed_cache_key(text), np_dumps(embedding))
            # fill in missing values
            ret[i] = embedding
    return ret


def _embed_cache_key(text: str) -> str:
    return "gooey/openai_ada2_embeddings_npy/v1/" + _sha256(text)


def _sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def np_loads(data: bytes) -> np.ndarray:
    return np.load(io.BytesIO(data))


def np_dumps(a: np.ndarray) -> bytes:
    f = io.BytesIO()
    np.save(f, a)
    return f.getvalue()


@do_retry()
def _openai_embedding_create(
    *, input: list[str], model: str = "text-embedding-ada-002"
) -> np.ndarray:
    import openai

    res = openai.Embedding.create(model=model, input=input)
    ret = np.array([data["embedding"] for data in res["data"]])

    # see - https://community.openai.com/t/text-embedding-ada-002-embeddings-sometime-return-nan/279664/5
    if np.isnan(ret).any():
        raise RuntimeError("NaNs detected in embedding")
        # raise openai.error.APIError("NaNs detected in embedding")  # this lets us retry
    expected = (len(input), 1536)
    if ret.shape != expected:
        raise RuntimeError(
            f"Unexpected shape for embedding: {ret.shape} (expected {expected})"
        )

    return ret


class ConversationEntry(typing_extensions.TypedDict):
    role: str
    display_name: typing_extensions.NotRequired[str]
    content: str


def _run_chat_model(
    *,
    messages: list[dict],
    max_tokens: int,
    num_outputs: int,
    temperature: float,
    engine: str = "gpt-3.5-turbo",
    stop: list[str] = None,
    avoid_repetition: bool = False,
) -> list[dict]:
    import openai

    r = openai.ChatCompletion.create(
        model=engine,
        messages=messages,
        max_tokens=max_tokens,
        stop=stop,
        n=num_outputs,
        temperature=temperature,
        frequency_penalty=0.1 if avoid_repetition else 0,
        presence_penalty=0.25 if avoid_repetition else 0,
    )
    return [
        {
            "role": choice["message"]["role"],
            "content": choice["message"]["content"].strip(),
        }
        for choice in r["choices"]
    ]


@do_retry()
def run_language_model(
    *,
    api_provider: str = "openai",
    model: str,
    prompt: str = None,
    messages: list[dict] = None,
    max_tokens: int = 512,
    quality: float = 1.0,
    num_outputs: int = 1,
    temperature: float = 0.7,
    stop: list[str] = None,
    avoid_repetition: bool = False,
) -> list[str]:
    import openai

    assert bool(prompt) != bool(
        messages
    ), "Pleave provide exactly one of { prompt, messages }"

    model = LargeLanguageModels[model]
    if model.is_chat_model():
        if messages:
            is_chatml = False
        else:
            # if input is chatml, parse out the json messages
            is_chatml, messages = parse_chatml(prompt)
        messages = _run_chat_model(
            engine=engine_names[model],
            messages=messages,
            max_tokens=max_tokens,
            num_outputs=num_outputs,
            temperature=temperature,
            stop=stop,
            avoid_repetition=avoid_repetition,
        )
        return [
            # return messages back as either chatml or json messages
            format_chatml_message(entry) if is_chatml else entry["content"]
            for entry in messages
        ]
    r = openai.Completion.create(
        engine=engine_names[model],
        prompt=prompt,
        max_tokens=max_tokens,
        stop=stop,
        best_of=int(num_outputs * quality),
        n=num_outputs,
        temperature=temperature,
        frequency_penalty=0.1 if avoid_repetition else 0,
        presence_penalty=0.25 if avoid_repetition else 0,
    )
    return [choice["text"].strip() for choice in r["choices"]]


def format_chatml_message(entry: ConversationEntry) -> str:
    msg = CHATML_START_TOKEN + entry.get("role", "")
    content = entry.get("content")
    if content:
        msg += "\n" + content + CHATML_END_TOKEN
    return msg


chatml_re = re.compile(
    re.escape(CHATML_START_TOKEN) + r"(.*)$",
    flags=re.M,
)


def parse_chatml(prompt: str) -> (bool, list[dict]):
    splits = chatml_re.split(prompt)
    is_chatml = len(splits) > 1
    if is_chatml:
        messages = []
        for i in range(1, len(splits) - 1, 2):
            role = splits[i].strip()
            content = (
                splits[i + 1]
                .replace(CHATML_START_TOKEN, "")
                .replace(CHATML_END_TOKEN, "")
                .strip()
            )
            messages.append({"role": role, "content": content})
    else:
        messages = [
            {"role": "system", "content": DEFAULT_SYSTEM_MSG},
            {"role": "user", "content": prompt},
        ]
    return is_chatml, messages
