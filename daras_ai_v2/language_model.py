import hashlib
import io
import json
import re
import typing
from enum import Enum
from functools import partial
from typing import Iterator

import numpy as np
import requests
import typing_extensions
from aifail import (
    openai_should_retry,
    retry_if,
    vertex_ai_should_retry,
    try_all,
)
from django.conf import settings
from jinja2.lexer import whitespace_re
from loguru import logger
from openai.types.chat import ChatCompletionContentPartParam
from openai.types.chat.chat_completion_chunk import ChoiceDelta

from daras_ai_v2.asr import get_google_auth_session
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.functions import LLMTools
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
    gpt_4_vision = "GPT-4 Vision (openai)"
    gpt_4_turbo = "GPT-4 Turbo (openai)"
    gpt_4 = "GPT-4 (openai)"
    gpt_4_32k = "GPT-4 32K (openai)"
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

    def is_vision_model(self) -> bool:
        return self in {
            self.gpt_4_vision,
        }

    def is_chat_model(self) -> bool:
        return self not in {
            self.palm2_text,
            self.text_davinci_003,
            self.text_davinci_002,
            self.text_curie_001,
            self.text_babbage_001,
            self.text_ada_001,
            self.code_davinci_002,
        }


AZURE_OPENAI_MODEL_PREFIX = "openai-"

llm_model_names = {
    LargeLanguageModels.gpt_4_vision: "gpt-4-vision-preview",
    LargeLanguageModels.gpt_4_turbo: (
        "openai-gpt-4-turbo-prod-ca-1",
        "gpt-4-1106-preview",
    ),
    LargeLanguageModels.gpt_4: (
        "openai-gpt-4-prod-ca-1",
        "gpt-4",
    ),
    LargeLanguageModels.gpt_4_32k: "openai-gpt-4-32k-prod-ca-1",
    LargeLanguageModels.gpt_3_5_turbo: (
        "openai-gpt-35-turbo-prod-ca-1",
        "gpt-3.5-turbo",
    ),
    LargeLanguageModels.gpt_3_5_turbo_16k: (
        "openai-gpt-35-turbo-16k-prod-ca-1",
        "gpt-3.5-turbo-16k",
    ),
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
    LargeLanguageModels.gpt_4_vision: LLMApis.openai,
    LargeLanguageModels.gpt_4_turbo: LLMApis.openai,
    LargeLanguageModels.gpt_4: LLMApis.openai,
    LargeLanguageModels.gpt_4_32k: LLMApis.openai,
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
    # https://platform.openai.com/docs/models/gpt-4-and-gpt-4-turbo
    LargeLanguageModels.gpt_4_vision: 128_000,
    # https://help.openai.com/en/articles/8555510-gpt-4-turbo
    LargeLanguageModels.gpt_4_turbo: 128_000,
    # https://platform.openai.com/docs/models/gpt-4
    LargeLanguageModels.gpt_4: 8192,
    LargeLanguageModels.gpt_4_32k: 32_768,
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

llm_price = {
    LargeLanguageModels.gpt_4_vision: 6,
    LargeLanguageModels.gpt_4_turbo: 5,
    LargeLanguageModels.gpt_4: 10,
    LargeLanguageModels.gpt_4_32k: 20,
    LargeLanguageModels.gpt_3_5_turbo: 1,
    LargeLanguageModels.gpt_3_5_turbo_16k: 2,
    LargeLanguageModels.text_davinci_003: 10,
    LargeLanguageModels.text_davinci_002: 10,
    LargeLanguageModels.code_davinci_002: 10,
    LargeLanguageModels.text_curie_001: 5,
    LargeLanguageModels.text_babbage_001: 2,
    LargeLanguageModels.text_ada_001: 1,
    LargeLanguageModels.palm2_text: 15,
    LargeLanguageModels.palm2_chat: 10,
    LargeLanguageModels.llama2_70b_chat: 5,
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
        embeddings = _run_openai_embedding(input=[texts[i] for i in misses])
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


@retry_if(openai_should_retry)
def _run_openai_embedding(
    *,
    input: list[str],
    model: str = (
        "openai-text-embedding-ada-002-prod-ca-1",
        "text-embedding-ada-002",
    ),
) -> np.ndarray:
    logger.info(f"{model=}, {len(input)=}")

    if isinstance(model, str):
        model = [model]
    res = try_all(
        *[
            partial(
                _get_openai_client(model_str).embeddings.create,
                model=model_str,
                input=input,
            )
            for model_str in model
        ],
    )
    ret = np.array([data.embedding for data in res.data])

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
    role: typing.Literal["user", "system", "assistant", "tool"]
    content: str | list[ChatCompletionContentPartParam]
    display_name: typing_extensions.NotRequired[str]


def get_entry_images(entry: ConversationEntry) -> list[str]:
    contents = entry.get("content") or ""
    if isinstance(contents, str):
        return []
    return list(
        filter(None, (part.get("image_url", {}).get("url") for part in contents)),
    )


def get_entry_text(entry: ConversationEntry) -> str:
    contents = entry.get("content") or ""
    if isinstance(contents, str):
        return contents
    return "\n".join(
        filter(None, (part.get("text") for part in contents)),
    )


def run_language_model(
    *,
    model: str,
    prompt: str = None,
    messages: list[ConversationEntry] = None,
    max_tokens: int = 512,
    quality: float = 1.0,
    num_outputs: int = 1,
    temperature: float = 0.7,
    stop: list[str] = None,
    avoid_repetition: bool = False,
    tools: list[LLMTools] | None = None,
    response_format_type: typing.Literal["text", "json_object"] = "text",
    stream: bool = False,
) -> Iterator[list[str]] | list[str] | tuple[list[str], list[list[dict]]]:
    assert bool(prompt) != bool(
        messages
    ), "Pleave provide exactly one of { prompt, messages }"
    if stream:
        assert (
            response_format_type == "text"
        ), "Only text output is supported with streaming"
        assert not tools, "Tools are not yet supported with streaming"

    llm = LargeLanguageModels[model]
    api = llm_api[llm]
    model_name = llm_model_names[llm]
    if llm.is_chat_model():
        if messages:
            is_chatml = False
        else:
            # if input is chatml, convert it into json messages
            is_chatml, messages = parse_chatml(prompt)  # type: ignore
        messages = messages or []
        logger.info(f"{model_name=}, {len(messages)=}, {max_tokens=}, {temperature=}")
        if not llm.is_vision_model():
            messages = [
                format_chat_entry(role=entry["role"], content=get_entry_text(entry))
                for entry in messages
            ]
        chat_result = _run_chat_model(
            api=api,
            model=model_name,
            messages=messages,  # type: ignore
            max_tokens=max_tokens,
            num_outputs=num_outputs,
            temperature=temperature,
            stop=stop,
            avoid_repetition=avoid_repetition,
            tools=tools,
            stream=stream,
            response_format_type=response_format_type,
        )

        if stream:
            chat_result_iterator = stream_chat_result(
                chat_result,
                num_outputs=num_outputs,
                is_chatml=is_chatml,
            )
            return _stream_outputs(num_outputs, chat_result_iterator)

        entries = next(chat_result)

        if response_format_type == "json_object":
            out_content = [json.loads(entry["content"]) for entry in entries]
        else:
            out_content = [
                # return messages back as either chatml or json messages
                format_chatml_message(entry)
                if is_chatml
                else (entry.get("content") or "").strip()
                for entry in entries
            ]

        if tools:
            return out_content, [(entry.get("tool_calls") or []) for entry in entries]
        else:
            return out_content

    else:
        if tools:
            raise ValueError("Only OpenAI chat models support Tools")
        if stream:
            raise ValueError("Only OpenAI chat models support streaming")
        logger.info(f"{model_name=}, {len(prompt)=}, {max_tokens=}, {temperature=}")
        result = _run_text_model(
            api=api,
            model=model_name,
            prompt=prompt,
            max_tokens=max_tokens,
            num_outputs=num_outputs,
            temperature=temperature,
            stop=stop,
            avoid_repetition=avoid_repetition,
            quality=quality,
        )
        return [msg.strip() for msg in result]


def _stream_outputs(
    num_outputs: int, result: typing.Iterator[list[str]]
) -> Iterator[list[str]]:
    outputs: list[str] = ["" for _ in range(num_outputs)]
    streamed_text_lengths: list[int] = [0 for _ in range(num_outputs)]
    streamed_text_counts: list[int] = [0 for _ in range(num_outputs)]
    for updated_texts in result:
        for i, updated_text in enumerate(updated_texts):
            if breaking_index := _get_breaking_index(
                updated_text,
                streamed_text_lengths[i],
                streamed_text_counts[i],
            ):
                streamed_text_lengths[i] = breaking_index
                streamed_text_counts[i] += 1
                outputs[i] = updated_text[: breaking_index + 1]
                yield outputs

    yield updated_texts


def _get_breaking_index(text: str, streamed_length: int, streamed_count: int):
    match streamed_count:
        case 0:
            if len(text) < 100:
                return None
            newline_rindex = text.rfind("\n", 100)
            newline_index = text.find("\n", 100)
            period_rindex = text.rfind(". ", 100)
            period_index = text.find(". ", 100)
            if newline_index != -1 and newline_rindex != newline_index:
                return newline_rindex
            elif period_index != -1 and period_rindex != period_index:
                return period_rindex + 1
            else:
                return None
        case 1:
            if len(text) < streamed_length + 100:
                return None
            if text[streamed_length + 100 :].count("\n") >= 3:
                return text.rfind("\n")
            elif text[streamed_length + 100 :].count(". ") >= 5:
                return text.rfind(". ") + 1
            else:
                return None
        case _:
            return None


def stream_chat_result(
    chat_result: Iterator[list[ConversationEntry]],
    is_chatml: bool,
    num_outputs: int,
) -> Iterator[list[str]]:
    entries: list[ConversationEntry] = [
        {"role": "assistant", "content": ""} for _ in range(num_outputs)
    ]
    for partial_entries in chat_result:
        for i, part in enumerate(partial_entries):
            entries[i]["role"] = part["role"]
            entries[i]["content"] += part.get("content", "")  # type: ignore
        yield [
            format_chatml_message(entry)
            if is_chatml
            else str(entry.get("content") or "")
            for entry in entries
        ]


def _run_text_model(
    *,
    api: LLMApis,
    model: str | tuple,
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
            return _run_openai_text(
                model=model,
                prompt=prompt,
                max_tokens=max_tokens,
                num_outputs=num_outputs,
                temperature=temperature,
                stop=stop,
                avoid_repetition=avoid_repetition,
                quality=quality,
            )
        case LLMApis.vertex_ai:
            return _run_palm_text(
                model_id=model,
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
    model: str | tuple,
    stop: list[str] | None,
    avoid_repetition: bool,
    stream: bool,
    tools: list[LLMTools] | None,
    response_format_type: typing.Literal["text", "json_object"],
) -> Iterator[list[ConversationEntry]]:
    match api:
        case LLMApis.openai:
            result = _run_openai_chat(
                model=model,
                avoid_repetition=avoid_repetition,
                max_tokens=max_tokens,
                messages=messages,
                num_outputs=num_outputs,
                stop=stop,
                temperature=temperature,
                tools=tools,
                stream=stream,
                response_format_type=response_format_type,
            )
            yield from result
        case LLMApis.vertex_ai:
            if tools:
                raise ValueError("Only OpenAI chat models support Tools")
            if stream:
                raise ValueError("Only OpenAI chat models support streaming")
            yield _run_palm_chat(
                model_id=model,
                messages=messages,
                max_output_tokens=min(max_tokens, 1024),  # because of Vertex AI limits
                candidate_count=num_outputs,
                temperature=temperature,
            )
        case LLMApis.together:
            if tools:
                raise ValueError("Only OpenAI chat models support Tools")
            if stream:
                raise ValueError("Only OpenAI chat models support streaming")
            yield _run_together_chat(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                num_outputs=num_outputs,
                temperature=temperature,
                repetition_penalty=1.15 if avoid_repetition else 1,
            )
        case _:
            raise ValueError(f"Unsupported chat api: {api}")


@retry_if(openai_should_retry)
def _run_openai_chat(
    *,
    model: str | list[str],
    messages: list[ConversationEntry],
    max_tokens: int,
    num_outputs: int,
    temperature: float,
    stop: list[str] | None,
    avoid_repetition: bool,
    stream: bool,
    tools: list[LLMTools] | None,
    response_format_type: typing.Literal["text", "json_object"],
) -> Iterator[list[ConversationEntry]]:
    from openai._types import NOT_GIVEN

    if avoid_repetition:
        frequency_penalty = 0.1
        presence_penalty = 0.25
    else:
        frequency_penalty = 0
        presence_penalty = 0
    if isinstance(model, str):
        model = [model]

    partials = [
        partial(
            _get_openai_client(model_str).chat.completions.create,
            model=model_str,
            messages=messages,
            max_tokens=max_tokens,
            stop=stop or NOT_GIVEN,
            n=num_outputs,
            temperature=temperature,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            tools=[tool.spec for tool in tools] if tools else NOT_GIVEN,
            stream=stream,
            response_format={"type": response_format_type}
            if response_format_type
            else NOT_GIVEN,
        )
        for model_str in model
    ]

    if stream:
        # NOTE: retries not supported for streaming yet
        stream_fn = partials[0]
        for chunk in stream_fn():
            outputs: list[ConversationEntry] = [
                {"role": "assistant", "content": ""} for _ in range(num_outputs)
            ]
            for choice in chunk.choices:
                outputs[choice.index] = choice_delta_to_entry(choice.delta)
            yield outputs
    else:
        r = try_all(*partials)
        yield [choice.message.dict() for choice in r.choices]


@retry_if(openai_should_retry)
def _run_openai_text(
    model: str,
    prompt: str,
    max_tokens: int,
    num_outputs: int,
    temperature: float,
    stop: list[str] | None,
    avoid_repetition: bool,
    quality: float,
):
    r = _get_openai_client(model).completions.create(
        model=model,
        prompt=prompt,
        max_tokens=max_tokens,
        stop=stop,
        best_of=int(num_outputs * quality),
        n=num_outputs,
        temperature=temperature,
        frequency_penalty=0.1 if avoid_repetition else 0,
        presence_penalty=0.25 if avoid_repetition else 0,
    )
    return [choice.text for choice in r.choices]


def _get_openai_client(model: str) -> "openai.OpenAI | openai.AzureOpenAI":
    import openai

    if model.startswith(AZURE_OPENAI_MODEL_PREFIX):
        client = openai.AzureOpenAI(
            api_key=settings.AZURE_OPENAI_KEY,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_version="2023-10-01-preview",
            max_retries=0,
        )
    else:
        client = openai.OpenAI(
            api_key=settings.OPENAI_API_KEY,
            max_retries=0,
        )
    return client


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


@retry_if(vertex_ai_should_retry)
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


@retry_if(vertex_ai_should_retry)
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
    msg = CHATML_START_TOKEN + (entry.get("role") or "")
    content = get_entry_text(entry).strip()
    if content:
        msg += "\n" + content + CHATML_END_TOKEN
    return msg


def choice_delta_to_entry(
    delta: ChoiceDelta,
    *,
    default_role: str = "assistant",
) -> ConversationEntry:
    return {"role": delta.role or default_role, "content": delta.content or ""}


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


def format_chat_entry(
    *, role: str, content: str, images: list[str] = None
) -> ConversationEntry:
    if images:
        content = [
            {"type": "image_url", "image_url": {"url": url}} for url in images
        ] + [
            {"type": "text", "text": content},
        ]
    return {"role": role, "content": content}
