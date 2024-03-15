import json
import mimetypes
import re
import typing
from enum import Enum
from functools import wraps

import requests
import typing_extensions
from aifail import (
    openai_should_retry,
    retry_if,
    vertex_ai_should_retry,
    try_all,
)
from django.conf import settings
from loguru import logger
from openai.types.chat import (
    ChatCompletionContentPartParam,
    ChatCompletionChunk,
)

from daras_ai.image_input import gs_url_to_uri
from daras_ai_v2.asr import get_google_auth_session
from daras_ai_v2.exceptions import raise_for_status, UserError
from daras_ai_v2.functions import LLMTools
from daras_ai_v2.text_splitter import (
    default_length_function,
    default_separators,
)

DEFAULT_SYSTEM_MSG = "You are an intelligent AI assistant. Follow the instructions as closely as possible."

CHATML_START_TOKEN = "<|im_start|>"
CHATML_END_TOKEN = "<|im_end|>"

CHATML_ROLE_SYSTEM = "system"
CHATML_ROLE_ASSISTANT = "assistant"
CHATML_ROLE_USER = "user"

# nice for showing streaming progress
SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


class LLMApis(Enum):
    palm2 = 1
    gemini = 2
    openai = 3
    # together = 4
    groq = 5


class LargeLanguageModels(Enum):
    gpt_4_vision = "GPT-4 Vision (openai)"
    gpt_4_turbo = "GPT-4 Turbo (openai)"
    gpt_4 = "GPT-4 (openai)"
    gpt_4_32k = "GPT-4 32K (openai)"
    gpt_3_5_turbo = "ChatGPT (openai)"
    gpt_3_5_turbo_16k = "ChatGPT 16k (openai)"
    gpt_3_5_turbo_instruct = "GPT-3.5 Instruct (openai)"

    llama2_70b_chat = "Llama 2 70b Chat (Meta AI)"
    mixtral_8x7b_instruct_0_1 = "Mixtral 8x7b Instruct v0.1 (Mistral)"
    gemma_7b_it = "Gemma 7B (Google)"

    gemini_1_pro = "Gemini 1.0 Pro (Google)"
    gemini_1_pro_vision = "Gemini 1.0 Pro Vision (Google)"
    palm2_chat = "PaLM 2 Chat (Google)"
    palm2_text = "PaLM 2 Text (Google)"

    text_davinci_003 = "GPT-3.5 Davinci-3 [Deprecated] (openai)"
    text_davinci_002 = "GPT-3.5 Davinci-2 [Deprecated] (openai)"
    text_curie_001 = "Curie [Deprecated] (openai)"
    text_babbage_001 = "Babbage [Deprecated] (openai)"
    text_ada_001 = "Ada [Deprecated] (openai)"

    code_davinci_002 = "Codex [Deprecated] (openai)"

    @classmethod
    def _deprecated(cls):
        return {
            cls.text_davinci_003,
            cls.text_davinci_002,
            cls.text_curie_001,
            cls.text_babbage_001,
            cls.text_ada_001,
            cls.code_davinci_002,
        }

    def is_vision_model(self) -> bool:
        return self in {
            self.gpt_4_vision,
            self.gemini_1_pro_vision,
        }

    def is_chat_model(self) -> bool:
        return self not in {
            self.gpt_3_5_turbo_instruct,
            self.palm2_text,
            self.gemini_1_pro_vision,
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
        "gpt-3.5-turbo-0613",
    ),
    LargeLanguageModels.gpt_3_5_turbo_16k: (
        "openai-gpt-35-turbo-16k-prod-ca-1",
        "gpt-3.5-turbo-16k-0613",
    ),
    LargeLanguageModels.gpt_3_5_turbo_instruct: "gpt-3.5-turbo-instruct",
    LargeLanguageModels.text_davinci_003: "text-davinci-003",
    LargeLanguageModels.text_davinci_002: "text-davinci-002",
    LargeLanguageModels.code_davinci_002: "code-davinci-002",
    LargeLanguageModels.text_curie_001: "text-curie-001",
    LargeLanguageModels.text_babbage_001: "text-babbage-001",
    LargeLanguageModels.text_ada_001: "text-ada-001",
    LargeLanguageModels.palm2_text: "text-bison",
    LargeLanguageModels.palm2_chat: "chat-bison",
    LargeLanguageModels.gemini_1_pro: "gemini-1.0-pro",
    LargeLanguageModels.gemini_1_pro_vision: "gemini-1.0-pro-vision",
    LargeLanguageModels.llama2_70b_chat: "llama2-70b-4096",
    LargeLanguageModels.mixtral_8x7b_instruct_0_1: "mixtral-8x7b-32768",
    LargeLanguageModels.gemma_7b_it: "gemma-7b-it",
}

llm_api = {
    LargeLanguageModels.gpt_4_vision: LLMApis.openai,
    LargeLanguageModels.gpt_4_turbo: LLMApis.openai,
    LargeLanguageModels.gpt_4: LLMApis.openai,
    LargeLanguageModels.gpt_4_32k: LLMApis.openai,
    LargeLanguageModels.gpt_3_5_turbo: LLMApis.openai,
    LargeLanguageModels.gpt_3_5_turbo_16k: LLMApis.openai,
    LargeLanguageModels.gpt_3_5_turbo_instruct: LLMApis.openai,
    LargeLanguageModels.text_davinci_003: LLMApis.openai,
    LargeLanguageModels.text_davinci_002: LLMApis.openai,
    LargeLanguageModels.code_davinci_002: LLMApis.openai,
    LargeLanguageModels.text_curie_001: LLMApis.openai,
    LargeLanguageModels.text_babbage_001: LLMApis.openai,
    LargeLanguageModels.text_ada_001: LLMApis.openai,
    LargeLanguageModels.gemini_1_pro: LLMApis.gemini,
    LargeLanguageModels.gemini_1_pro_vision: LLMApis.gemini,
    LargeLanguageModels.palm2_text: LLMApis.palm2,
    LargeLanguageModels.palm2_chat: LLMApis.palm2,
    LargeLanguageModels.llama2_70b_chat: LLMApis.groq,
    LargeLanguageModels.mixtral_8x7b_instruct_0_1: LLMApis.groq,
    LargeLanguageModels.gemma_7b_it: LLMApis.groq,
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
    LargeLanguageModels.gpt_3_5_turbo_instruct: 4096,
    LargeLanguageModels.text_davinci_003: 4097,
    LargeLanguageModels.text_davinci_002: 4097,
    LargeLanguageModels.code_davinci_002: 8001,
    # https://platform.openai.com/docs/models/gpt-3
    LargeLanguageModels.text_curie_001: 2049,
    LargeLanguageModels.text_babbage_001: 2049,
    LargeLanguageModels.text_ada_001: 2049,
    # https://cloud.google.com/vertex-ai/docs/generative-ai/learn/models
    LargeLanguageModels.gemini_1_pro: 8192,
    LargeLanguageModels.gemini_1_pro_vision: 2048,
    LargeLanguageModels.palm2_text: 8192,
    LargeLanguageModels.palm2_chat: 4096,
    # https://console.groq.com/docs/models
    LargeLanguageModels.llama2_70b_chat: 4096,
    LargeLanguageModels.mixtral_8x7b_instruct_0_1: 32_768,
    LargeLanguageModels.gemma_7b_it: 8_192,
}

llm_price = {
    LargeLanguageModels.gpt_4_vision: 6,
    LargeLanguageModels.gpt_4_turbo: 5,
    LargeLanguageModels.gpt_4: 10,
    LargeLanguageModels.gpt_4_32k: 20,
    LargeLanguageModels.gpt_3_5_turbo: 1,
    LargeLanguageModels.gpt_3_5_turbo_16k: 2,
    LargeLanguageModels.gpt_3_5_turbo_instruct: 1,
    LargeLanguageModels.text_davinci_003: 10,
    LargeLanguageModels.text_davinci_002: 10,
    LargeLanguageModels.code_davinci_002: 10,
    LargeLanguageModels.text_curie_001: 5,
    LargeLanguageModels.text_babbage_001: 2,
    LargeLanguageModels.text_ada_001: 1,
    LargeLanguageModels.gemini_1_pro: 15,
    LargeLanguageModels.gemini_1_pro_vision: 25,
    LargeLanguageModels.palm2_text: 15,
    LargeLanguageModels.palm2_chat: 10,
    LargeLanguageModels.llama2_70b_chat: 1,
    LargeLanguageModels.mixtral_8x7b_instruct_0_1: 1,
    LargeLanguageModels.gemma_7b_it: 1,
}


def calc_gpt_tokens(
    prompt: str | list[str] | dict | list[dict],
    *,
    sep: str = "",
) -> int:
    if isinstance(prompt, (str, dict)):
        messages = [prompt]
    else:
        messages = prompt
    combined = sep.join(
        (format_chatml_message(entry) + "\n") if isinstance(entry, dict) else str(entry)
        for entry in messages
    )
    return default_length_function(combined)


class ConversationEntry(typing_extensions.TypedDict):
    role: typing.Literal["user", "system", "assistant"]
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
    tools: list[LLMTools] = None,
    stream: bool = False,
    response_format_type: typing.Literal["text", "json_object"] = None,
) -> (
    list[str]
    | tuple[list[str], list[list[dict]]]
    | typing.Generator[list[dict], None, None]
):
    assert bool(prompt) != bool(
        messages
    ), "Pleave provide exactly one of { prompt, messages }"

    model: LargeLanguageModels = LargeLanguageModels[str(model)]
    api = llm_api[model]
    model_name = llm_model_names[model]
    is_chatml = False
    if model.is_chat_model():
        if not messages:
            # if input is chatml, convert it into json messages
            is_chatml, messages = parse_chatml(prompt)  # type: ignore
        messages = messages or []
        logger.info(f"{model_name=}, {len(messages)=}, {max_tokens=}, {temperature=}")
        if not model.is_vision_model():
            messages = [
                format_chat_entry(role=entry["role"], content=get_entry_text(entry))
                for entry in messages
            ]
        entries = _run_chat_model(
            api=api,
            model=model_name,
            messages=messages,  # type: ignore
            max_tokens=max_tokens,
            num_outputs=num_outputs,
            temperature=temperature,
            stop=stop,
            avoid_repetition=avoid_repetition,
            tools=tools,
            response_format_type=response_format_type,
            # we can't stream with tools or json yet
            stream=stream and not (tools or response_format_type),
        )

        if stream:
            return _stream_llm_outputs(entries, response_format_type)
        else:
            return _parse_entries(entries, is_chatml, response_format_type, tools)
    else:
        if tools:
            raise ValueError("Only OpenAI chat models support Tools")
        images = []
        if not prompt:
            # assistant prompt to triger a model response
            messages.append({"role": CHATML_ROLE_ASSISTANT, "content": ""})
            # for backwards compat with non-chat models
            prompt = "\n".join(format_chatml_message(entry) for entry in messages)
            stop = [CHATML_END_TOKEN, CHATML_START_TOKEN]
            for entry in reversed(messages):
                images = get_entry_images(entry)
                if images:
                    break
        logger.info(f"{model_name=}, {len(prompt)=}, {max_tokens=}, {temperature=}")
        msgs = _run_text_model(
            api=api,
            model=model_name,
            prompt=prompt,
            images=images,
            max_tokens=max_tokens,
            num_outputs=num_outputs,
            temperature=temperature,
            stop=stop,
            avoid_repetition=avoid_repetition,
            quality=quality,
        )
        ret = [msg.strip() for msg in msgs]
        if stream:
            ret = [
                [
                    format_chat_entry(role=CHATML_ROLE_ASSISTANT, content=msg)
                    for msg in ret
                ]
            ]
        return ret


def _stream_llm_outputs(
    result: list | typing.Generator[list[ConversationEntry], None, None],
    response_format_type: typing.Literal["text", "json_object"] | None,
):
    if isinstance(result, list):  # compatibility with non-streaming apis
        result = [result]
    for entries in result:
        if response_format_type == "json_object":
            for i, entry in enumerate(entries):
                entries[i] = json.loads(entry["content"])
        for i, entry in enumerate(entries):
            entries[i]["content"] = entry.get("content") or ""
        yield entries


def _parse_entries(
    entries: list[dict],
    is_chatml: bool,
    response_format_type: typing.Literal["text", "json_object"] | None,
    tools: list[dict] | None,
):
    if response_format_type == "json_object":
        ret = [json.loads(entry["content"]) for entry in entries]
    else:
        ret = [
            # return messages back as either chatml or json messages
            (
                format_chatml_message(entry)
                if is_chatml
                else (entry.get("content") or "").strip()
            )
            for entry in entries
        ]
    if tools:
        return ret, [(entry.get("tool_calls") or []) for entry in entries]
    else:
        return ret


def _run_text_model(
    *,
    api: LLMApis,
    model: str | tuple,
    prompt: str,
    images: list[str],
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
        case LLMApis.palm2:
            return _run_palm_text(
                model_id=model,
                prompt=prompt,
                max_output_tokens=min(max_tokens, 1024),  # because of Vertex AI limits
                candidate_count=num_outputs,
                temperature=temperature,
                stop=stop,
            )
        case LLMApis.gemini:
            return _run_gemini_pro_vision(
                model_id=model,
                prompt=prompt,
                images=images,
                max_output_tokens=min(max_tokens, 1024),  # because of Vertex AI limits
                temperature=temperature,
                stop=stop,
            )
        case _:
            raise UserError(f"Unsupported text api: {api}")


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
    tools: list[LLMTools] | None,
    response_format_type: typing.Literal["text", "json_object"] | None,
    stream: bool = False,
) -> list[ConversationEntry] | typing.Generator[list[ConversationEntry], None, None]:
    match api:
        case LLMApis.openai:
            return _run_openai_chat(
                model=model,
                avoid_repetition=avoid_repetition,
                max_tokens=max_tokens,
                messages=messages,
                num_outputs=num_outputs,
                stop=stop,
                temperature=temperature,
                tools=tools,
                response_format_type=response_format_type,
                stream=stream,
            )
        case LLMApis.gemini:
            if tools:
                raise ValueError("Only OpenAI chat models support Tools")
            return _run_gemini_pro(
                model_id=model,
                messages=messages,
                max_output_tokens=min(max_tokens, 1024),  # because of Vertex AI limits
                temperature=temperature,
            )
        case LLMApis.palm2:
            if tools:
                raise ValueError("Only OpenAI chat models support Tools")
            return _run_palm_chat(
                model_id=model,
                messages=messages,
                max_output_tokens=min(max_tokens, 1024),  # because of Vertex AI limits
                candidate_count=num_outputs,
                temperature=temperature,
            )
        case LLMApis.groq:
            if tools:
                raise ValueError("Only OpenAI chat models support Tools")
            return _run_groq_chat(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                avoid_repetition=avoid_repetition,
                stop=stop,
            )
        # case LLMApis.together:
        #     if tools:
        #         raise UserError("Only OpenAI chat models support Tools")
        #     return _run_together_chat(
        #         model=model,
        #         messages=messages,
        #         max_tokens=max_tokens,
        #         num_outputs=num_outputs,
        #         temperature=temperature,
        #         repetition_penalty=1.15 if avoid_repetition else 1,
        #     )
        case _:
            raise UserError(f"Unsupported chat api: {api}")


@retry_if(openai_should_retry)
def _run_openai_chat(
    *,
    model: str,
    messages: list[ConversationEntry],
    max_tokens: int,
    num_outputs: int,
    temperature: float,
    stop: list[str] | None,
    avoid_repetition: bool,
    tools: list[LLMTools] | None,
    response_format_type: typing.Literal["text", "json_object"] | None,
    stream: bool = False,
) -> list[ConversationEntry] | typing.Generator[list[ConversationEntry], None, None]:
    from openai._types import NOT_GIVEN

    if avoid_repetition:
        frequency_penalty = 0.1
        presence_penalty = 0.25
    else:
        frequency_penalty = 0
        presence_penalty = 0
    if isinstance(model, str):
        model = [model]
    r, used_model = try_all(
        *[
            _get_chat_completions_create(
                model=model_str,
                messages=messages,
                max_tokens=max_tokens,
                stop=stop or NOT_GIVEN,
                n=num_outputs,
                temperature=temperature,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                tools=[tool.spec for tool in tools] if tools else NOT_GIVEN,
                response_format=(
                    {"type": response_format_type}
                    if response_format_type
                    else NOT_GIVEN
                ),
                stream=stream,
            )
            for model_str in model
        ],
    )
    if stream:
        return _stream_openai_chunked(r, used_model, messages)
    else:
        ret = [choice.message.dict() for choice in r.choices]
        record_openai_llm_usage(used_model, messages, ret)
        return ret


def _get_chat_completions_create(model: str, **kwargs):
    client = get_openai_client(model)

    @wraps(client.chat.completions.create)
    def wrapper():
        return client.chat.completions.create(model=model, **kwargs), model

    return wrapper


def _stream_openai_chunked(
    r: typing.Iterable[ChatCompletionChunk],
    used_model: str,
    messages: list[ConversationEntry],
    *,
    start_chunk_size: int = 50,
    stop_chunk_size: int = 400,
    step_chunk_size: int = 150,
) -> typing.Generator[list[ConversationEntry], None, None]:
    ret = []
    chunk_size = start_chunk_size

    for completion_chunk in r:
        changed = False
        for choice in completion_chunk.choices:
            delta = choice.delta
            try:
                # get the entry for this choice
                entry = ret[choice.index]
            except IndexError:
                # initialize the entry
                entry = delta.dict() | {"content": "", "chunk": ""}
                ret.append(entry)
            # this is to mark the end of streaming
            entry["finish_reason"] = choice.finish_reason

            # append the delta to the current chunk
            if not delta.content:
                continue
            entry["chunk"] += delta.content
            # if the chunk is too small, we need to wait for more data
            chunk = entry["chunk"]
            if len(chunk) < chunk_size:
                continue

            # iterate through the separators and find the best one that matches
            for sep in default_separators[:-1]:
                # find the last occurrence of the separator
                match = None
                for match in re.finditer(sep, chunk):
                    pass
                if not match:
                    continue  # no match, try the next separator or wait for more data
                # append text before the separator to the content
                part = chunk[: match.end()]
                if len(part) < chunk_size:
                    continue  # not enough text, try the next separator or wait for more data
                entry["content"] += part
                # set text after the separator as the next chunk
                entry["chunk"] = chunk[match.end() :]
                # increase the chunk size, but don't go over the max
                chunk_size = min(chunk_size + step_chunk_size, stop_chunk_size)
                # we found a separator, so we can stop looking and yield the partial result
                changed = True
                break
        if changed:
            yield ret

    # add the leftover chunks
    for entry in ret:
        entry["content"] += entry["chunk"]
    yield ret

    record_openai_llm_usage(used_model, messages, ret)


def record_openai_llm_usage(
    used_model: str, messages: list[ConversationEntry], choices: list[ConversationEntry]
):
    from usage_costs.cost_utils import record_cost_auto
    from usage_costs.models import ModelSku

    record_cost_auto(
        model=used_model,
        sku=ModelSku.llm_prompt,
        quantity=sum(
            default_length_function(get_entry_text(entry)) for entry in messages
        ),
    )
    record_cost_auto(
        model=used_model,
        sku=ModelSku.llm_completion,
        quantity=sum(
            default_length_function(get_entry_text(entry)) for entry in choices
        ),
    )


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
    r = get_openai_client(model).completions.create(
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

    from usage_costs.cost_utils import record_cost_auto
    from usage_costs.models import ModelSku

    record_cost_auto(
        model=model,
        sku=ModelSku.llm_prompt,
        quantity=r.usage.prompt_tokens,
    )
    record_cost_auto(
        model=model,
        sku=ModelSku.llm_completion,
        quantity=r.usage.completion_tokens,
    )

    return [choice.text for choice in r.choices]


def get_openai_client(model: str):
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


def _run_groq_chat(
    *,
    model: str,
    messages: list[ConversationEntry],
    max_tokens: int,
    temperature: float,
    avoid_repetition: bool,
    stop: list[str] | None,
):
    data = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if avoid_repetition:
        data["frequency_penalty"] = 0.1
        data["presence_penalty"] = 0.25
    if stop:
        data["stop"] = stop
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        json=data,
        headers={
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        },
    )
    raise_for_status(r)
    out = r.json()
    return [choice["message"] for choice in out["choices"]]


# def _run_together_chat(
#     *,
#     model: str,
#     messages: list[ConversationEntry],
#     max_tokens: int,
#     temperature: float,
#     repetition_penalty: float,
#     num_outputs: int,
# ) -> list[ConversationEntry]:
#     """
#     Args:
#         model: The model version to use for the request.
#         messages: List of messages to generate model response. Will be converted to a single prompt.
#         max_tokens: The maximum number of tokens to generate.
#         temperature: The randomness of the prediction. This value must be between 0 and 1, inclusive. 0 means deterministic.
#         repetition_penalty: Penalty for repeated words in generated text; 1 is no penalty, values greater than 1 discourage repetition, less than 1 encourage it.
#         num_outputs: The number of responses to generate.
#     """
#     results = map_parallel(
#         lambda _: requests.post(
#             "https://api.together.xyz/inference",
#             json={
#                 "model": model,
#                 "prompt": build_llama_prompt(messages),
#                 "max_tokens": max_tokens,
#                 "stop": [B_INST],
#                 "temperature": temperature,
#                 "repetition_penalty": repetition_penalty,
#             },
#             headers={
#                 "Authorization": f"Bearer {settings.TOGETHER_API_KEY}",
#             },
#         ),
#         range(num_outputs),
#     )
#     ret = []
#     prompt_tokens = 0
#     completion_tokens = 0
#     for r in results:
#         raise_for_status(r)
#         data = r.json()
#         output = data["output"]
#         error = output.get("error")
#         if error:
#             raise ValueError(error)
#         ret.append(
#             {
#                 "role": CHATML_ROLE_ASSISTANT,
#                 "content": output["choices"][0]["text"],
#             }
#         )
#         prompt_tokens += output.get("usage", {}).get("prompt_tokens", 0)
#         completion_tokens += output.get("usage", {}).get("completion_tokens", 0)
#     from usage_costs.cost_utils import record_cost_auto
#     from usage_costs.models import ModelSku
#
#     record_cost_auto(
#         model=model,
#         sku=ModelSku.llm_prompt,
#         quantity=prompt_tokens,
#     )
#     record_cost_auto(
#         model=model,
#         sku=ModelSku.llm_completion,
#         quantity=completion_tokens,
#     )
#     return ret


gemini_role_map = {
    CHATML_ROLE_SYSTEM: "user",
    CHATML_ROLE_USER: "user",
    CHATML_ROLE_ASSISTANT: "model",
}


@retry_if(vertex_ai_should_retry)
def _run_gemini_pro(
    *,
    model_id: str,
    messages: list[ConversationEntry],
    max_output_tokens: int,
    temperature: float,
):
    contents = []
    for entry in messages:
        contents.append(
            {
                "role": gemini_role_map[entry["role"]],
                "parts": [{"text": get_entry_text(entry)}],
            },
        )
        if entry["role"] == CHATML_ROLE_SYSTEM:
            contents.append(
                {
                    "role": "model",
                    "parts": [{"text": "OK"}],
                },
            )
    msg = _call_gemini_api(
        model_id=model_id,
        contents=contents,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
    )
    return [{"role": CHATML_ROLE_ASSISTANT, "content": msg}]


def _run_gemini_pro_vision(
    *,
    model_id: str,
    prompt: str,
    images: list[str],
    max_output_tokens: int,
    temperature: float,
    stop: list[str] = None,
):
    contents = [
        {
            "role": gemini_role_map[CHATML_ROLE_USER],
            "parts": [
                {"text": prompt},
            ]
            + [
                {
                    "fileData": {
                        "mimeType": mimetypes.guess_type(image)[0] or "image/png",
                        "fileUri": gs_url_to_uri(image),
                    },
                }
                for image in images
            ],
        }
    ]
    return [
        _call_gemini_api(
            model_id=model_id,
            contents=contents,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            stop=stop,
        )
    ]


@retry_if(vertex_ai_should_retry)
def _call_gemini_api(
    *,
    model_id: str,
    contents: list[dict],
    max_output_tokens: int,
    temperature: float,
    stop: list[str] = None,
) -> str:
    session, project = get_google_auth_session()
    r = session.post(
        f"https://{settings.GCP_REGION}-aiplatform.googleapis.com/v1/projects/{project}/locations/{settings.GCP_REGION}/publishers/google/models/{model_id}:streamGenerateContent",
        json={
            "contents": contents,
            "generation_config": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
                "stopSequences": stop or [],
            },
        },
    )
    raise_for_status(r)
    ret = "".join(
        parts[0]["text"]
        for item in r.json()
        for msg in item["candidates"]
        if (parts := msg["content"].get("parts"))
    )

    from usage_costs.cost_utils import record_cost_auto
    from usage_costs.models import ModelSku

    record_cost_auto(
        model=model_id,
        sku=ModelSku.llm_prompt,
        quantity=sum(
            len(part.get("text") or "") for item in contents for part in item["parts"]
        ),
    )
    record_cost_auto(
        model=model_id,
        sku=ModelSku.llm_completion,
        quantity=len(ret),
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
        f"https://{settings.GCP_REGION}-aiplatform.googleapis.com/v1/projects/{project}/locations/{settings.GCP_REGION}/publishers/google/models/{model_id}:predict",
        json={
            "instances": [instance],
            "parameters": {
                "maxOutputTokens": max_output_tokens,
                "temperature": temperature,
                "candidateCount": candidate_count,
            },
        },
    )
    raise_for_status(r)
    out = r.json()
    ret = [
        {
            "role": msg["author"],
            "content": msg["content"],
        }
        for pred in out["predictions"]
        for msg in pred["candidates"]
    ]

    from usage_costs.cost_utils import record_cost_auto
    from usage_costs.models import ModelSku

    record_cost_auto(
        model=model_id,
        sku=ModelSku.llm_prompt,
        quantity=sum(len(get_entry_text(entry)) for entry in messages),
    )
    record_cost_auto(
        model=model_id,
        sku=ModelSku.llm_completion,
        quantity=sum(len(msg["content"] or "") for msg in ret),
    )

    return ret


@retry_if(vertex_ai_should_retry)
def _run_palm_text(
    *,
    model_id: str,
    prompt: str,
    max_output_tokens: int,
    candidate_count: int,
    temperature: float,
    stop: list[str] = None,
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
        f"https://{settings.GCP_REGION}-aiplatform.googleapis.com/v1/projects/{project}/locations/{settings.GCP_REGION}/publishers/google/models/{model_id}:predict",
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
                "stopSequences": stop or [],
            },
        },
    )
    raise_for_status(res)
    out = res.json()

    from usage_costs.cost_utils import record_cost_auto
    from usage_costs.models import ModelSku

    record_cost_auto(
        model=model_id,
        sku=ModelSku.llm_prompt,
        quantity=out["metadata"]["tokenMetadata"]["inputTokenCount"]["totalTokens"],
    )
    record_cost_auto(
        model=model_id,
        sku=ModelSku.llm_completion,
        quantity=out["metadata"]["tokenMetadata"]["outputTokenCount"]["totalTokens"],
    )

    return [prediction["content"] for prediction in out["predictions"]]


def format_chatml_message(entry: ConversationEntry) -> str:
    msg = CHATML_START_TOKEN + entry.get("role", "")
    content = get_entry_text(entry).strip()
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
