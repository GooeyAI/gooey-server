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

import requests
from django.conf import settings

from daras_ai_v2.redis_cache import (
    get_redis_cache,
)
from daras_ai_v2.asr import get_google_auth_session

DEFAULT_SYSTEM_MSG = "You are an intelligent AI assistant. Follow the instructions as closely as possible."

CHATML_START_TOKEN = "<|im_start|>"
CHATML_END_TOKEN = "<|im_end|>"

CHATML_ROLE_SYSTEM = "system"
CHATML_ROLE_ASSISSTANT = "assistant"
CHATML_ROLE_USER = "user"


class LLMApis(Enum):
    vertex_ai = "Vertex AI"
    openai = "OpenAI"
    together = "Together"


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

    palm2_text = "PaLM 2 (text-bison)"
    palm2_chat = "PaLM 2 (chat-bison)"

    llama2_70b_chat = "LLAMA 2.0 (70B, chat)"

    def is_chat_model(self) -> bool:
        return self in [
            LargeLanguageModels.gpt_4,
            LargeLanguageModels.gpt_3_5_turbo,
            LargeLanguageModels.gpt_3_5_turbo_16k,
            LargeLanguageModels.palm2_chat,
            LargeLanguageModels.llama2_70b_chat,
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
    LargeLanguageModels.palm2_text: "text-bison",
    LargeLanguageModels.palm2_chat: "chat-bison",
    LargeLanguageModels.llama2_70b_chat: "togethercomputer/llama-2-70b-chat",
}

llm_api = {
    LargeLanguageModels.gpt_4: LLMApis.openai,
    LargeLanguageModels.gpt_3_5_turbo: LLMApis.openai,
    LargeLanguageModels.gpt_3_5_turbo_16k: LLMApis.openai,
    LargeLanguageModels.text_davinci_003: LLMApis.openai,
    LargeLanguageModels.text_davinci_002: LLMApis.openai,
    LargeLanguageModels.code_davinci_002: LLMApis.openai,
    LargeLanguageModels.text_curie_001: LLMApis.openai,
    LargeLanguageModels.text_babbage_001: LLMApis.openai,
    LargeLanguageModels.text_ada_001: LLMApis.openai,
    LargeLanguageModels.palm2_text: LLMApis.vertex_ai,
    LargeLanguageModels.palm2_chat: LLMApis.vertex_ai,
    LargeLanguageModels.llama2_70b_chat: LLMApis.together,
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
    # https://cloud.google.com/vertex-ai/docs/generative-ai/learn/models
    LargeLanguageModels.palm2_text: 8192,
    LargeLanguageModels.palm2_chat: 4096,
    # https://huggingface.co/docs/transformers/main/model_doc/llama2#transformers.LlamaConfig.max_position_embeddings and https://huggingface.co/TheBloke/Llama-2-13B-chat-GPTQ/discussions/7
    LargeLanguageModels.llama2_70b_chat: 1024,
}

threadlocal = threading.local()


def calc_gpt_tokens(
    text: str | list[str] | dict | list[dict],
    *,
    sep: str = "",
    is_chat_model: bool = True,
) -> int:
    try:
        enc = threadlocal.gpt2enc
    except AttributeError:
        enc = tiktoken.get_encoding("gpt2")
        threadlocal.gpt2enc = enc
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


def get_openai_error_cls():
    import openai.error

    return (
        openai.error.Timeout,
        openai.error.APIError,
        openai.error.APIConnectionError,
        openai.error.RateLimitError,
        openai.error.ServiceUnavailableError,
    )


def get_vertex_ai_error_cls():
    import google.api_core.exceptions

    return (
        google.api_core.exceptions.DeadlineExceeded,
        google.api_core.exceptions.ServiceUnavailable,
        google.api_core.exceptions.TooManyRequests,
        google.api_core.exceptions.InternalServerError,
        google.api_core.exceptions.GatewayTimeout,
        google.api_core.exceptions.ResourceExhausted,
    )


def do_retry(
    max_retries: int = 5,
    retry_delay: float = 5,
    get_error_cls=lambda: get_openai_error_cls() + get_vertex_ai_error_cls(),
) -> typing.Callable[
    [typing.Callable[..., typing.Any]], typing.Callable[..., typing.Any]
]:
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


def openai_embedding_create(texts: list[str]) -> list[np.ndarray | None]:
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
    ret = np.array([data["embedding"] for data in res["data"]])  # type: ignore

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
    api: LLMApis = LLMApis.openai,
    messages: list[ConversationEntry],
    max_tokens: int,
    num_outputs: int,
    temperature: float,
    engine: str = "gpt-3.5-turbo",
    stop: list[str] | None = None,
    avoid_repetition: bool = False,
) -> list[ConversationEntry]:
    import openai

    if api == LLMApis.openai:
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
            for choice in r["choices"]  # type: ignore
        ]
    elif api == LLMApis.vertex_ai:
        return _run_palm_chat(
            model_id=engine,
            messages=messages,
            maxOutputTokens=max_tokens,
            num_outputs=num_outputs,
            temperature=temperature,
        )
    elif api == LLMApis.together:
        return _run_together_chat(
            version=engine,
            messages=messages,
            max_new_tokens=max_tokens,
            num_outputs=num_outputs,
            temperature=temperature,
            repetition_penalty=1.15 if avoid_repetition else 1,
        )
    else:
        raise ValueError(f"Unknown api: {api}")


def _run_together_chat(
    version: str,
    messages: list[ConversationEntry],
    max_new_tokens: int = 1024,
    temperature: float = 0.7,
    top_p: float = 0.7,
    top_k: int = 50,
    repetition_penalty: float = 1,
    num_outputs: int = 1,
) -> list[ConversationEntry]:
    """
    Args:
        version: The model version to use for the request.
        messages: List of messages to generate model response. Will be converted to a single prompt.
        max_new_tokens: The maximum number of tokens to generate.
        min_new_tokens: The minimum number of tokens to generate. To disable, set to -1.
        temperature: The randomness of the prediction. This value must be between 0 and 1, inclusive. 0 means deterministic.
        top_p: Cumulative probability of top vocabulary tokens to select from. This value must be between 0 and 1, inclusive.
        top_k: The number of highest probability vocabulary tokens to select from.
        repetition_penalty: Penalty for repeated words in generated text; 1 is no penalty, values greater than 1 discourage repetition, less than 1 encourage it.
        debug: Whether to provide debugging output in logs
        num_outputs: The number of responses to generate.
    """
    messages = [
        message for message in messages if message.get("role") != CHATML_ROLE_SYSTEM
    ]
    prompt = "\n\n".join([format_chatml_message(message) for message in messages])

    outputs = []

    for _ in range(num_outputs):
        res = requests.post(
            "https://api.together.xyz/inference",
            json={
                "model": version,
                "max_tokens": max_new_tokens,
                "prompt": f"[INST] {prompt} [/INST]",
                "request_type": "language-model-inference",
                "temperature": temperature,
                "top_p": top_p,
                "top_k": top_k,
                "repetition_penalty": repetition_penalty,
                "stop": ["[INST]"],
                "safety_model": "",
                "repetitive_penalty": 1,
            },
            headers={
                "Authorization": f"Bearer {settings.TOGETHER_API_KEY}",
            },
        )
        res.raise_for_status()
        response = res.json()["output"]["choices"][0]["text"]

        outputs += [
            {
                "role": CHATML_ROLE_ASSISSTANT,
                "content": "".join(response),
            }
        ]
    return outputs


def _run_palm_chat(
    model_id: str,
    messages: list[ConversationEntry],
    context: str | None = None,
    examples: list[dict] = [],
    maxOutputTokens: int = 0,
    topK: int = 40,
    topP: float = 0.95,
    num_outputs: int = 1,
    temperature: float = 0.0,
) -> list[ConversationEntry]:
    """
    Args:
        model_id: The model id to use for the request. See available models: https://cloud.google.com/vertex-ai/docs/generative-ai/learn/models
        messages: List of messages to generate model response.
        context: Optional context to use for the request.
        examples: Optional examples to use for the request. Each dict has an "input" and "output" dict with a single key "content".
        maxOutputTokens: The maximum number of tokens to generate. This value must be between 1 and 1024, inclusive. 0 means no limit.
        topK: The number of highest probability vocabulary tokens to select from. This value must be between 1 and 40, inclusive.
        topP: Cumulative probability of top vocabulary tokens to select from. This value must be between 0 and 1, inclusive.
        num_outputs: The number of responses to generate.
        temperature: The randomness of the prediction. This value must be between 0 and 1, inclusive. 0 means deterministic. 0.2 recommended by Google.
    """
    session, project = get_google_auth_session()
    outputs = []

    # load system messages as context, TODO: label examples correctly too
    for message in messages:
        if message.get("role") == CHATML_ROLE_SYSTEM:
            if not context:
                context = ""
            context += "\n" + message.get("content", "")
    messages = [
        message for message in messages if message.get("role") != CHATML_ROLE_SYSTEM
    ]

    config: dict[str, typing.Any] = {
        "messages": [
            {"author": message["role"], "content": message["content"]}
            for message in messages
        ],
    }
    if context:
        config["context"] = context
    if examples:
        config["examples"] = examples

    for _ in range(num_outputs):
        res = session.post(
            f"https://us-central1-aiplatform.googleapis.com/v1/projects/{project}/locations/us-central1/publishers/google/models/{model_id}:predict",
            json={
                "instances": [config],
                "parameters": {
                    "maxOutputTokens": maxOutputTokens,
                    "topK": topK,
                    "topP": topP,
                    "temperature": temperature,
                },
            },
        )
        res.raise_for_status()
        outputs += [
            {"role": candidate["author"], "content": candidate["content"]}
            for candidate in res.json()["predictions"][0]["candidates"]
        ]
    return outputs


def _run_palm(
    model_id: str,
    prompt: str,
    maxOutputTokens: int = 0,
    topK: int = 40,
    topP: float = 0.95,
    num_outputs: int = 1,
    temperature: float = 0.0,
) -> list[str]:
    """
    Args:
        model_id: The model id to use for the request. See available models: https://cloud.google.com/vertex-ai/docs/generative-ai/learn/models
        prompt: Text input to generate model response. Prompts can include preamble, questions, suggestions, instructions, or examples.
        maxOutputTokens: The maximum number of tokens to generate. This value must be between 1 and 1024, inclusive. 0 means no limit.
        topK: The number of highest probability vocabulary tokens to select from. This value must be between 1 and 40, inclusive.
        topP: Cumulative probability of top vocabulary tokens to select from. This value must be between 0 and 1, inclusive.
        num_outputs: The number of responses to generate.
        temperature: The randomness of the prediction. This value must be between 0 and 1, inclusive. 0 means deterministic. 0.2 recommended by Google.
    """
    session, project = get_google_auth_session()
    outputs = []
    for _ in range(num_outputs):
        res = session.post(
            f"https://us-central1-aiplatform.googleapis.com/v1/projects/{project}/locations/us-central1/publishers/google/models/{model_id}:predict",
            json={
                "instances": [
                    {
                        "prompt": prompt,
                    }
                ],
                "parameters": {
                    "maxOutputTokens": maxOutputTokens,
                    "topK": topK,
                    "topP": topP,
                    "temperature": temperature,
                },
            },
        )
        res.raise_for_status()
        outputs += [prediction["content"] for prediction in res.json()["predictions"]]
    return outputs


@do_retry()
def run_language_model(
    *,
    model: tuple[[e.name for e in LargeLanguageModels]],  # type: ignore
    prompt: str | None = None,
    messages: list[ConversationEntry] | None = None,  # type: ignore
    max_tokens: int = 512,
    quality: float = 1.0,
    num_outputs: int = 1,
    temperature: float = 0.7,
    stop: list[str] | None = None,
    avoid_repetition: bool = False,
) -> list[str]:
    import openai

    assert bool(prompt) != bool(
        messages
    ), "Pleave provide exactly one of { prompt, messages }"

    model: LargeLanguageModels = LargeLanguageModels[str(model)]
    api = llm_api[model]
    if model.is_chat_model():
        if messages:
            is_chatml = False
        else:
            # if input is chatml, parse out the json messages
            is_chatml, messages = parse_chatml(prompt)  # type: ignore
        messages: list[ConversationEntry] = _run_chat_model(
            api=api,
            engine=engine_names[model],
            messages=messages or [],  # type: ignore
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
    if api == LLMApis.openai:
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
        return [choice["text"].strip() for choice in r["choices"]]  # type: ignore
    elif api == LLMApis.vertex_ai:
        return _run_palm(
            model_id=engine_names[model],
            prompt=prompt,  # type: ignore
            maxOutputTokens=max_tokens,
            num_outputs=num_outputs,
            temperature=temperature,
        )
    else:
        raise ValueError(f"Unknown api: {api}")


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


def parse_chatml(prompt: str) -> tuple[bool, list[dict]]:
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
