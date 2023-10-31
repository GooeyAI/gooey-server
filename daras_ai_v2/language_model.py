import hashlib
import io
import re
import threading
import typing
from enum import Enum
from functools import wraps
from time import sleep

import numpy as np
import requests
import tiktoken
import typing_extensions
from django.conf import settings
from jinja2.lexer import whitespace_re

from daras_ai_v2.asr import get_google_auth_session
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.redis_cache import (
    get_redis_cache,
)
from daras_ai_v2.text_splitter import default_length_function

DEFAULT_SYSTEM_MSG = "You are an intelligent AI assistant. Follow the instructions as closely as possible."

CHATML_START_TOKEN = "<|im_start|>"
CHATML_END_TOKEN = "<|im_end|>"

CHATML_ROLE_SYSTEM = "system"
CHATML_ROLE_ASSISTANT = "assistant"
CHATML_ROLE_USER = "user"


class LLMApis(Enum):
    vertex_ai = "Vertex AI"
    openai = "OpenAI"
    together = "Together"


class LargeLanguageModels(Enum):
    gpt_4 = "GPT-4 (openai)"
    gpt_3_5_turbo = "ChatGPT (openai)"
    gpt_3_5_turbo_16k = "ChatGPT 16k (openai)"

    llama2_70b_chat = "Llama 2 (Meta AI)"
    palm2_chat = "PaLM 2 Text (Google)"

    palm2_text = "PaLM 2 Chat (Google)"

    text_davinci_003 = "GPT-3.5 Davinci-3 (openai)"
    text_davinci_002 = "GPT-3.5 Davinci-2 (openai)"
    text_curie_001 = "Curie (openai)"
    text_babbage_001 = "Babbage (openai)"
    text_ada_001 = "Ada (openai)"

    code_davinci_002 = "Codex [Deprecated] (openai)"

    @classmethod
    def _deprecated(cls):
        return {cls.code_davinci_002}

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

EMBEDDING_MODEL_MAX_TOKENS = 8191

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
    # https://huggingface.co/docs/transformers/main/model_doc/llama2#transformers.LlamaConfig.max_position_embeddings
    LargeLanguageModels.llama2_70b_chat: 4096,
}


def calc_gpt_tokens(
    text: str | list[str] | dict | list[dict],
    *,
    sep: str = "",
    is_chat_model: bool = True,
) -> int:
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
    return default_length_function(combined)


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
        google.api_core.exceptions.ServiceUnavailable,
        google.api_core.exceptions.TooManyRequests,
        google.api_core.exceptions.InternalServerError,
        google.api_core.exceptions.GatewayTimeout,
    )


def do_retry(
    max_retries: int = 10,
    retry_delay: float = 6,
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
                        print(f"({n}/5) captured error, retry in {retry_delay}s: {e!r}")
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


@do_retry()
def run_language_model(
    *,
    model: str,
    prompt: str | None = None,
    messages: list[ConversationEntry] | None = None,
    max_tokens: int = 512,  # Default value version 1.0
    quality: float = 1.0,  # Default value version 1.0
    num_outputs: int = 1,  # Default value version 1.0
    temperature: float = 0.7,  # Default value version 1.0
    stop: list[str] | None = None,
    avoid_repetition: bool = False,
) -> list[str]:
    assert bool(prompt) != bool(
        messages
    ), "Pleave provide exactly one of { prompt, messages }"

    model: LargeLanguageModels = LargeLanguageModels[str(model)]
    api = llm_api[model]
    if model.is_chat_model():
        if messages:
            is_chatml = False
        else:
            # if input is chatml, convert it into json messages
            is_chatml, messages = parse_chatml(prompt)  # type: ignore
        result = _run_chat_model(
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
            format_chatml_message(entry) if is_chatml else entry["content"].strip()
            for entry in result
        ]
    else:
        result = _run_text_model(
            api=api,
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            num_outputs=num_outputs,
            temperature=temperature,
            stop=stop,
            avoid_repetition=avoid_repetition,
            quality=quality,
        )
        return [msg.strip() for msg in result]


def _run_text_model(
    *,
    api: LLMApis,
    model: LargeLanguageModels,
    prompt: str,
    max_tokens: int,
    num_outputs: int,
    temperature: float,
    stop: list[str] | None,
    avoid_repetition: bool,
    quality: float,
) -> list[str]:
    match api:
        case LLMApis.openai:
            import openai

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
            return [choice["text"] for choice in r["choices"]]
        case LLMApis.vertex_ai:
            return _run_palm_text(
                model_id=engine_names[model],
                prompt=prompt,
                max_output_tokens=min(max_tokens, 1024),  # because of Vertex AI limits
                candidate_count=num_outputs,
                temperature=temperature,
            )
        case _:
            raise ValueError(f"Unsupported text api: {api}")


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
    match api:
        case LLMApis.openai:
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
            return [choice["message"] for choice in r["choices"]]
        case LLMApis.vertex_ai:
            return _run_palm_chat(
                model_id=engine,
                messages=messages,
                max_output_tokens=min(max_tokens, 1024),  # because of Vertex AI limits
                candidate_count=num_outputs,
                temperature=temperature,
            )
        case LLMApis.together:
            return _run_together_chat(
                model=engine,
                messages=messages,
                max_tokens=max_tokens,
                num_outputs=num_outputs,
                temperature=temperature,
                repetition_penalty=1.15 if avoid_repetition else 1,
            )
        case _:
            raise ValueError(f"Unsupported chat api: {api}")


def _run_together_chat(
    *,
    model: str,
    messages: list[ConversationEntry],
    max_tokens: int,
    temperature: float,
    repetition_penalty: float,
    num_outputs: int,
) -> list[ConversationEntry]:
    """
    Args:
        model: The model version to use for the request.
        messages: List of messages to generate model response. Will be converted to a single prompt.
        max_tokens: The maximum number of tokens to generate.
        temperature: The randomness of the prediction. This value must be between 0 and 1, inclusive. 0 means deterministic.
        repetition_penalty: Penalty for repeated words in generated text; 1 is no penalty, values greater than 1 discourage repetition, less than 1 encourage it.
        num_outputs: The number of responses to generate.
    """
    results = map_parallel(
        lambda _: requests.post(
            "https://api.together.xyz/inference",
            json={
                "model": model,
                "prompt": build_llama_prompt(messages),
                "max_tokens": max_tokens,
                "stop": [B_INST],
                "temperature": temperature,
                "repetition_penalty": repetition_penalty,
            },
            headers={
                "Authorization": f"Bearer {settings.TOGETHER_API_KEY}",
            },
        ),
        range(num_outputs),
    )
    ret = []
    for r in results:
        r.raise_for_status()
        data = r.json()
        output = data["output"]
        error = output.get("error")
        if error:
            raise ValueError(error)
        ret.append(
            {
                "role": CHATML_ROLE_ASSISTANT,
                "content": output["choices"][0]["text"],
            }
        )
    return ret


def _run_palm_chat(
    *,
    model_id: str,
    messages: list[ConversationEntry],
    max_output_tokens: int,
    candidate_count: int,
    temperature: float,
) -> list[ConversationEntry]:
    """
    Args:
        model_id: The model id to use for the request. See available models: https://cloud.google.com/vertex-ai/docs/generative-ai/learn/models
        messages: List of messages to generate model response.
        max_output_tokens: The maximum number of tokens to generate. This value must be between 1 and 1024, inclusive. 0 means no limit.
        candidate_count: The number of response variations to return.
        temperature: The randomness of the prediction. This value must be between 0 and 1, inclusive. 0 means deterministic. 0.2 recommended by Google.
    """

    instance = dict(
        context="\n".join(
            msg.get("content", "")
            for msg in messages
            if msg.get("role") == CHATML_ROLE_SYSTEM
        ),
        messages=[
            {
                "author": msg["role"],
                "content": msg["content"],
            }
            for msg in messages
            if msg.get("role") != CHATML_ROLE_SYSTEM
        ],
    )

    session, project = get_google_auth_session()
    r = session.post(
        f"https://us-central1-aiplatform.googleapis.com/v1/projects/{project}/locations/us-central1/publishers/google/models/{model_id}:predict",
        json={
            "instances": [instance],
            "parameters": {
                "maxOutputTokens": max_output_tokens,
                "temperature": temperature,
                "candidateCount": candidate_count,
            },
        },
    )
    r.raise_for_status()

    return [
        {
            "role": msg["author"],
            "content": msg["content"],
        }
        for pred in r.json()["predictions"]
        for msg in pred["candidates"]
    ]


def _run_palm_text(
    *,
    model_id: str,
    prompt: str,
    max_output_tokens: int,
    candidate_count: int,
    temperature: float,
) -> list[str]:
    """
    Args:
        model_id: The model id to use for the request. See available models: https://cloud.google.com/vertex-ai/docs/generative-ai/learn/models
        prompt: Text input to generate model response. Prompts can include preamble, questions, suggestions, instructions, or examples.
        max_output_tokens: The maximum number of tokens to generate. This value must be between 1 and 1024, inclusive. 0 means no limit.
        candidate_count: The number of response variations to return.
        temperature: The randomness of the prediction. This value must be between 0 and 1, inclusive. 0 means deterministic. 0.2 recommended by Google.
    """
    session, project = get_google_auth_session()
    res = session.post(
        f"https://us-central1-aiplatform.googleapis.com/v1/projects/{project}/locations/us-central1/publishers/google/models/{model_id}:predict",
        json={
            "instances": [
                {
                    "prompt": prompt,
                }
            ],
            "parameters": {
                "maxOutputTokens": max_output_tokens,
                "temperature": temperature,
                "candidateCount": candidate_count,
            },
        },
    )
    res.raise_for_status()
    return [prediction["content"] for prediction in res.json()["predictions"]]


def format_chatml_message(entry: ConversationEntry) -> str:
    msg = CHATML_START_TOKEN + entry.get("role", "")
    content = entry.get("content").strip()
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


# This prompt formatting was copied from the original Llama v2 repo:
# https://github.com/facebookresearch/llama/blob/c769dfd53ddd509159216a5423204653850f79f4/llama/generation.py#L44
# These are components of the prompt that should not be changed by the users
B_INST, E_INST = "[INST]", "[/INST]"
B_SYS, E_SYS = "<<SYS>>\n", "\n<</SYS>>\n\n"

SPECIAL_TAGS = [B_INST, E_INST, B_SYS.strip(), E_SYS.strip()]


def build_llama_prompt(messages: list[ConversationEntry]):
    if any([tag in msg.get("content", "") for tag in SPECIAL_TAGS for msg in messages]):
        raise ValueError(
            f"Messages cannot contain any of the following: {SPECIAL_TAGS}"
        )

    if messages and messages[0]["role"] == CHATML_ROLE_SYSTEM:
        system_prompt = messages[0].get("content", "").strip()
        messages = messages[1:]
    else:
        system_prompt = ""

    if messages and messages[0]["role"] == CHATML_ROLE_USER:
        first_user_message = messages[0].get("content", "").strip()
        messages = messages[1:]
    else:
        first_user_message = ""

    if system_prompt:
        first_user_message = B_SYS + system_prompt + E_SYS + first_user_message
    messages = [
        {
            "role": CHATML_ROLE_USER,
            "content": first_user_message,
        },
    ] + messages

    assert all([msg["role"] == CHATML_ROLE_USER for msg in messages[::2]]) and all(
        [msg["role"] == CHATML_ROLE_ASSISTANT for msg in messages[1::2]]
    ), (
        f"llama only supports '{CHATML_ROLE_SYSTEM}', '{CHATML_ROLE_USER}' and '{CHATML_ROLE_ASSISTANT}' roles, "
        "starting with 'system', then 'user' and alternating (u/a/u/a/u...)"
    )

    if messages[-1]["role"] == CHATML_ROLE_ASSISTANT:
        messages.append({"role": CHATML_ROLE_USER, "content": ""})

    ret = "".join(
        f"{B_INST} {prompt.get('content', '').strip()} {E_INST} {answer.get('content', '').strip()} "
        for prompt, answer in zip(messages[::2], messages[1::2])
    )

    assert (
        messages[-1]["role"] == CHATML_ROLE_USER
    ), f"Last message must be from {CHATML_ROLE_USER}, got {messages[-1]['role']}"

    ret += f"{B_INST} {messages[-1].get('content').strip()} {E_INST}"

    return ret
