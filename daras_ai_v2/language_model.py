from __future__ import annotations

import base64
import json
import mimetypes
import re
import typing
from functools import wraps
from time import time

import aifail
import requests
import typing_extensions
from aifail import openai_should_retry, retry_if, vertex_ai_should_retry, try_all
from django.conf import settings
from furl import furl
from loguru import logger
from openai import Stream
from openai.types.chat import (
    ChatCompletionContentPartParam,
    ChatCompletionChunk,
    ChatCompletion,
    ChatCompletionMessageToolCallParam,
)
from openai.types.completion_usage import CompletionUsage
from openai.types.responses import (
    Response,
    ResponseCompletedEvent,
    ResponseStreamEvent,
    ResponseUsage,
)

from ai_models.models import AIModelSpec, ModelProvider
from bots.models import Platform
from daras_ai.image_input import gs_url_to_uri, bytes_to_cv2_img, cv2_img_to_bytes
from daras_ai_v2.asr import audio_url_to_wav, get_google_auth_session
from daras_ai_v2.custom_enum import GooeyEnum
from daras_ai_v2.exceptions import raise_for_status, UserError
from daras_ai_v2.gpu_server import call_celery_task
from daras_ai_v2.language_model_openai_audio import run_openai_audio
from daras_ai_v2.redis_cache import redis_cache_decorator
from daras_ai_v2.text_splitter import default_length_function, default_separators
from functions.recipe_functions import BaseLLMTool

import gooey_gui as gui

DEFAULT_JSON_PROMPT = (
    "Please respond directly in JSON format. "
    "Don't output markdown or HTML, instead print the JSON object directly without formatting."
)

CHATML_ROLE_SYSTEM = "system"
CHATML_ROLE_ASSISTANT = "assistant"
CHATML_ROLE_USER = "user"

EMBEDDING_MODEL_MAX_TOKENS = 8191

# nice for showing streaming progress
SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")

AZURE_OPENAI_MODEL_PREFIX = "openai-"


class _ReasoningEffort(typing.NamedTuple):
    name: str
    label: str
    thinking_budget: int


class ReasoningEffort(_ReasoningEffort, GooeyEnum):
    minimal = _ReasoningEffort(name="minimal", label="Minimal", thinking_budget=1024)
    low = _ReasoningEffort(name="low", label="Low", thinking_budget=4096)
    medium = _ReasoningEffort(name="medium", label="Medium", thinking_budget=8192)
    high = _ReasoningEffort(name="high", label="High", thinking_budget=24576)

    @classmethod
    def _deprecated(cls):
        return {cls.minimal}


def calc_gpt_tokens(
    prompt: str | list[str] | dict | list[dict],
) -> int:
    if isinstance(prompt, (str, dict)):
        messages = [prompt]
    else:
        messages = prompt
    combined = msgs_to_prompt_str(messages)
    return default_length_function(combined)


class ConversationEntry(typing_extensions.TypedDict, total=False):
    role: typing.Literal["user", "system", "assistant", "tool"]
    content: str | list[ChatCompletionContentPartParam]

    chunk: typing_extensions.NotRequired[str]

    tool_calls: typing_extensions.NotRequired[list[ChatCompletionMessageToolCallParam]]
    tool_call_id: typing_extensions.NotRequired[str]

    display_name: typing_extensions.NotRequired[str]


def remove_images_from_entry(entry: ConversationEntry) -> ConversationEntry | None:
    contents = entry.get("content") or ""
    if isinstance(contents, str):
        return entry

    new_contents = [part for part in contents if not part.get("image_url")]
    if new_contents:
        entry["content"] = new_contents
        return entry
    return None


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


ResponseFormatType = typing.Literal["text", "json_object"]


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
    tools: list[BaseLLMTool] = None,
    stream: bool = False,
    response_format_type: ResponseFormatType = None,
    reasoning_effort: ReasoningEffort.api_choices | None = None,
    audio_url: str | None = None,
    audio_session_extra: dict | None = None,
) -> (
    list[str]
    | tuple[list[str], list[list[dict]]]
    | typing.Generator[list[dict], None, None]
):
    assert bool(prompt) != bool(messages), (
        "Pleave provide exactly one of { prompt, messages }"
    )

    model: AIModelSpec = AIModelSpec.objects.get(name=model)

    if model.name == "gemini_live":
        raise UserError(
            "Gemini Live is not supported for text generation. Please use this from a Voice Deployment instead."
        )

    if model.is_deprecated:
        if not model.redirect_to:
            raise UserError(f"Model {model} is deprecated.")
        return run_language_model(**(locals() | {"model": model.redirect_to.name}))

    variables = gui.session_state.get("variables", {})
    if variables and variables.get("platform") == Platform.WEB.name:
        start_chunk_size = 0
        stop_chunk_size = 200
        step_chunk_size = 50
    else:
        start_chunk_size = 50
        stop_chunk_size = 400
        step_chunk_size = 300

    if model.llm_max_output_tokens:
        max_tokens = min(max_tokens, model.llm_max_output_tokens)
    if model.llm_is_chat_model:
        if prompt and not messages:
            # convert text prompt to chat messages
            messages = [
                format_chat_entry(role=CHATML_ROLE_USER, content_text=prompt),
            ]
        if model.llm_is_audio_model and not stream:
            # audio is only supported in streaming mode, fall back to text
            model = AIModelSpec.objects.get(name="gpt_4_o")
        if not model.llm_is_vision_model:
            # remove images from the messages
            messages = list(
                filter(None, (remove_images_from_entry(entry) for entry in messages))
            )
        if (
            messages
            and response_format_type == "json_object"
            and "JSON" not in str(messages).upper()
        ):
            if messages[0]["role"] != CHATML_ROLE_SYSTEM:
                messages.insert(
                    0,
                    format_chat_entry(
                        role=CHATML_ROLE_SYSTEM, content_text=DEFAULT_JSON_PROMPT
                    ),
                )
            else:
                messages[0]["content"] = "\n\n".join(
                    [get_entry_text(messages[0]), DEFAULT_JSON_PROMPT]
                )
        if not model.llm_supports_temperature:
            temperature = None
        if not model.llm_supports_json:
            response_format_type = None
        result = _run_chat_model(
            model=model,
            messages=messages,  # type: ignore
            max_tokens=max_tokens,
            num_outputs=num_outputs,
            temperature=temperature,
            stop=stop,
            avoid_repetition=avoid_repetition,
            tools=tools,
            response_format_type=response_format_type,
            reasoning_effort=reasoning_effort,
            # we can't stream with tools or json yet
            stream=stream and not response_format_type,
            audio_url=audio_url,
            audio_session_extra=audio_session_extra,
            start_chunk_size=start_chunk_size,
            stop_chunk_size=stop_chunk_size,
            step_chunk_size=step_chunk_size,
        )
        if stream:
            return output_stream_generator(result)
        else:
            return [get_entry_text(entry).strip() for entry in result]
    else:
        if tools:
            raise ValueError("Only OpenAI chat models support Tools")
        images = []
        if not prompt:
            # assistant prompt to triger a model response
            messages.append({"role": CHATML_ROLE_ASSISTANT, "content": ""})
            # for backwards compat with non-chat models
            prompt = msgs_to_prompt_str(messages)
            stop = [
                CHATML_ROLE_ASSISTANT + ": ",
                CHATML_ROLE_SYSTEM + ": ",
                CHATML_ROLE_USER + ": ",
            ]
            for entry in reversed(messages):
                images = get_entry_images(entry)
                if images:
                    break
        msgs = _run_text_model(
            api=model.provider,
            model=model.model_id,
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
                    format_chat_entry(role=CHATML_ROLE_ASSISTANT, content_text=msg)
                    for msg in ret
                ]
            ]
        return ret


def output_stream_generator(
    result: list | typing.Generator[list[ConversationEntry], None, None],
):
    if isinstance(result, list):  # compatibility with non-streaming apis
        result = [result]
    for entries in result:
        for i, entry in enumerate(entries):
            entries[i]["content"] = entry.get("content") or ""  # null safety
        yield entries


def _run_text_model(
    *,
    api: ModelProvider,
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
    logger.info(f"{api=} {model=}, {len(prompt)=}, {max_tokens=}, {temperature=}")
    match api:
        case ModelProvider.openai:
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
        case ModelProvider.google:
            return _run_gemini_pro_vision(
                model_id=model,
                prompt=prompt,
                images=images,
                max_output_tokens=min(max_tokens, 1024),  # because of Vertex AI limits
                temperature=temperature,
                stop=stop,
            )
        case ModelProvider.aks:
            return [
                _run_self_hosted_llm(
                    model_id=model,
                    text_inputs=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    avoid_repetition=avoid_repetition,
                    stop=stop,
                )
            ]
        case _:
            raise UserError(f"Unsupported text api: {api}")


def _run_chat_model(
    *,
    model: AIModelSpec,
    messages: list[ConversationEntry],
    max_tokens: int,
    num_outputs: int,
    temperature: float | None,
    stop: list[str] | None,
    avoid_repetition: bool,
    tools: list[BaseLLMTool] | None,
    response_format_type: ResponseFormatType | None,
    reasoning_effort: ReasoningEffort.api_choices | None,
    stream: bool = False,
    audio_url: str | None = None,
    audio_session_extra: dict | None = None,
    start_chunk_size: int,
    stop_chunk_size: int,
    step_chunk_size: int,
) -> list[ConversationEntry] | typing.Generator[list[ConversationEntry], None, None]:
    logger.info(
        f"{model.provider=} {model.model_id=}, {len(messages)=}, {max_tokens=}, {temperature=} {stop=} {stream=}"
    )
    match model.provider:
        case ModelProvider.mistral:
            return _run_mistral_chat(
                model=model.model_id,
                avoid_repetition=avoid_repetition,
                max_tokens=max_tokens,
                messages=messages,
                num_outputs=num_outputs,
                stop=stop,
                temperature=temperature,
                tools=tools,
                response_format_type=response_format_type,
            )
        case ModelProvider.fireworks:
            return _run_fireworks_chat(
                model=model.model_id,
                avoid_repetition=avoid_repetition,
                max_tokens=max_tokens,
                messages=messages,
                num_outputs=num_outputs,
                stop=stop,
                temperature=temperature,
                tools=tools,
                response_format_type=response_format_type,
            )
        case ModelProvider.openai_audio:
            return run_openai_audio(
                model=model,
                audio_url=audio_url,
                audio_session_extra=audio_session_extra,
                messages=messages,
                temperature=temperature,
                tools=tools,
            )
        case ModelProvider.openai:
            return run_openai_chat(
                model=model,
                avoid_repetition=avoid_repetition,
                max_tokens=max_tokens,
                messages=messages,
                num_outputs=num_outputs,
                stop=stop,
                temperature=temperature,
                tools=tools,
                response_format_type=response_format_type,
                reasoning_effort=reasoning_effort,
                stream=stream,
                start_chunk_size=start_chunk_size,
                stop_chunk_size=stop_chunk_size,
                step_chunk_size=step_chunk_size,
            )
        case ModelProvider.openai_responses:
            return run_openai_responses(
                model=model,
                max_output_tokens=max_tokens,
                messages=messages,
                temperature=temperature,
                tools=tools,
                response_format_type=response_format_type,
                reasoning_effort=reasoning_effort,
                stream=stream,
                start_chunk_size=start_chunk_size,
                stop_chunk_size=stop_chunk_size,
                step_chunk_size=step_chunk_size,
            )
        case ModelProvider.google:
            if tools:
                raise ValueError("Only OpenAI chat models support Tools")
            return _run_gemini_pro(
                model_id=model.model_id,
                messages=messages,
                max_output_tokens=max_tokens,
                temperature=temperature,
                response_format_type=response_format_type,
            )
        case ModelProvider.groq:
            return _run_groq_chat(
                model=model.model_id,
                messages=messages,
                max_tokens=max_tokens,
                tools=tools,
                temperature=temperature,
                avoid_repetition=avoid_repetition,
                response_format_type=response_format_type,
                stop=stop,
            )
        case ModelProvider.anthropic:
            return _run_anthropic_chat(
                model=model.model_id,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=stop,
                response_format_type=response_format_type,
            )
        case ModelProvider.aks:
            return [
                {
                    "role": CHATML_ROLE_ASSISTANT,
                    "content": _run_self_hosted_llm(
                        model_id=model.model_id,
                        text_inputs=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        avoid_repetition=avoid_repetition,
                        stop=stop,
                    ),
                },
            ]
        case _:
            raise UserError(f"Unsupported chat api: {model.provider}")


def _run_self_hosted_llm(
    *,
    model_id: str,
    text_inputs: list[ConversationEntry] | str,
    max_tokens: int,
    temperature: float,
    avoid_repetition: bool,
    stop: list[str] | None,
) -> str:
    from usage_costs.cost_utils import record_cost_auto
    from usage_costs.models import ModelSku

    # sea lion doesnt support system prompt
    if (
        not isinstance(text_inputs, str)
        and model_id == "aisingapore/sea-lion-7b-instruct"
    ):
        for i, entry in enumerate(text_inputs):
            if entry["role"] == CHATML_ROLE_SYSTEM:
                text_inputs[i]["role"] = CHATML_ROLE_USER
                text_inputs.insert(i + 1, dict(role=CHATML_ROLE_ASSISTANT, content=""))

    ret = call_celery_task(
        "llm.chat",
        pipeline=dict(
            model_id=model_id,
            fallback_chat_template_from="meta-llama/Llama-2-7b-chat-hf",
        ),
        inputs=dict(
            text_inputs=text_inputs,
            max_new_tokens=max_tokens,
            stop_strings=stop,
            temperature=temperature,
            repetition_penalty=1.15 if avoid_repetition else 1,
        ),
    )

    if usage := ret.get("usage"):
        record_cost_auto(
            model=model_id,
            sku=ModelSku.llm_prompt,
            quantity=usage["prompt_tokens"],
        )
        record_cost_auto(
            model=model_id,
            sku=ModelSku.llm_completion,
            quantity=usage["completion_tokens"],
        )

    return ret["generated_text"]


def _run_anthropic_chat(
    *,
    model: str,
    messages: list[ConversationEntry],
    max_tokens: int,
    temperature: float,
    stop: list[str] | None,
    response_format_type: ResponseFormatType | None,
):
    import anthropic
    from usage_costs.cost_utils import record_cost_auto
    from usage_costs.models import ModelSku

    system_msg = ""
    anthropic_msgs = []
    for msg in messages:
        role = msg.get("role") or CHATML_ROLE_USER
        if role == CHATML_ROLE_SYSTEM:
            system_msg += get_entry_text(msg)
            continue
        images = get_entry_images(msg)
        if images:
            img_bytes = requests.get(images[0]).content
            cv2_img = bytes_to_cv2_img(img_bytes)
            img_b64 = base64.b64encode(cv2_img_to_bytes(cv2_img)).decode()
            content = [
                # https://docs.anthropic.com/claude/reference/messages_post
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": img_b64,
                    },
                },
                {"type": "text", "text": get_entry_text(msg)},
            ]
        else:
            content = get_entry_text(msg)
        anthropic_msgs.append({"role": role, "content": content})

    if response_format_type == "json_object":
        kwargs = dict(
            tools=[
                {
                    "name": "json_output",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "response": {
                                "type": "object",
                                "description": "The response to the user's prompt as a JSON object.",
                            },
                        },
                    },
                }
            ],
            tool_choice={"type": "tool", "name": "json_output"},
        )
    else:
        kwargs = {}

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_msg,
        messages=anthropic_msgs,
        stop_sequences=stop,
        temperature=temperature,
        **kwargs,
    )

    record_cost_auto(
        model=model,
        sku=ModelSku.llm_prompt,
        quantity=response.usage.input_tokens,
    )
    record_cost_auto(
        model=model,
        sku=ModelSku.llm_completion,
        quantity=response.usage.output_tokens,
    )

    if response_format_type == "json_object":
        if response.stop_reason == "max_tokens":
            raise UserError(
                "Claude's response got cut off due to hitting the max_tokens limit, and the truncated response contains an incomplete tool use block. "
                "Please retry the request with a higher max_tokens value to get the full tool use. "
            ) from anthropic.AnthropicError(
                f"Hit {response.stop_reason=} when generating JSON: {response.content=}"
            )
        if response.stop_reason != "tool_use":
            raise UserError(
                "Claude was unable to generate a JSON response. Please retry the request with a different prompt, or try a different model."
            ) from anthropic.AnthropicError(
                f"Failed to generate JSON response: {response.stop_reason=} {response.content}"
            )
        for entry in response.content:
            if entry.type != "tool_use":
                continue
            response = entry.input
            if isinstance(response, dict):
                response = response.get("response", {})
            return [
                {
                    "role": CHATML_ROLE_ASSISTANT,
                    "content": json.dumps(response),
                }
            ]
    return [
        {
            "role": CHATML_ROLE_ASSISTANT,
            "content": "".join(entry.text for entry in response.content),
        }
    ]


@retry_if(openai_should_retry)
def run_openai_responses(
    *,
    model: AIModelSpec,
    messages: list[ConversationEntry],
    max_output_tokens: int,
    temperature: float | None = None,
    tools: list[BaseLLMTool] | None = None,
    response_format_type: ResponseFormatType | None = None,
    reasoning_effort: ReasoningEffort.api_choices | None = None,
    stream: bool = False,
    start_chunk_size: int,
    stop_chunk_size: int,
    step_chunk_size: int,
) -> list[ConversationEntry] | typing.Generator[list[ConversationEntry], None, None]:
    from daras_ai_v2.safety_checker import capture_openai_content_policy_violation

    kwargs = {}

    if model.llm_is_thinking_model:
        thinking_budget = ReasoningEffort.high.thinking_budget
        kwargs["reasoning"] = {"summary": "auto"}
        if reasoning_effort:
            re = ReasoningEffort.from_api(reasoning_effort)
            if re == ReasoningEffort.minimal:  # deprecated
                re = ReasoningEffort.low
            kwargs["reasoning"]["effort"] = re.name
        # add some extra tokens for thinking
        max_output_tokens = max(thinking_budget + 1000, max_output_tokens)

    if model.llm_max_output_tokens:
        # cap the max tokens at the model's max limit
        max_output_tokens = min(max_output_tokens, model.llm_max_output_tokens)

    kwargs["max_output_tokens"] = max_output_tokens

    if tools:
        kwargs["tools"] = [tool.spec_openai_responses for tool in tools]

    if response_format_type:
        kwargs["text"] = {"format": {"type": response_format_type}}

    if temperature is not None:
        kwargs["temperature"] = temperature

    model_ids = model.model_id
    if isinstance(model_ids, str):
        model_ids = [model_ids]

    with capture_openai_content_policy_violation():
        response, used_model = try_all(
            *[
                _get_responses_create(
                    model=model_id,
                    api_key=model.api_key,
                    base_url=model.base_url,
                    messages=messages,
                    stream=stream,
                    **kwargs,
                )
                for model_id in model_ids
            ],
        )
        if isinstance(response, Stream):
            return _stream_openai_responses(
                response,
                used_model,
                messages,
                start_chunk_size=start_chunk_size,
                stop_chunk_size=stop_chunk_size,
                step_chunk_size=step_chunk_size,
            )
        else:
            ret = []
            if response.output_text:
                ret.append(
                    {"role": CHATML_ROLE_ASSISTANT, "content": response.output_text}
                )
            else:
                # If no valid content found, return empty response
                ret = [format_chat_entry(role=CHATML_ROLE_ASSISTANT, content_text="")]

            record_openai_llm_usage(used_model, response, messages, ret)
            return ret


@retry_if(openai_should_retry)
def run_openai_chat(
    *,
    model: AIModelSpec,
    messages: list[ConversationEntry],
    max_tokens: int,
    num_outputs: int,
    temperature: float | None = None,
    stop: list[str] | None = None,
    avoid_repetition: bool = False,
    tools: list[BaseLLMTool] | None = None,
    response_format_type: ResponseFormatType | None = None,
    reasoning_effort: ReasoningEffort.api_choices | None = None,
    stream: bool = False,
    start_chunk_size: int,
    stop_chunk_size: int,
    step_chunk_size: int,
) -> list[ConversationEntry] | typing.Generator[list[ConversationEntry], None, None]:
    from openai import NOT_GIVEN
    from daras_ai_v2.safety_checker import capture_openai_content_policy_violation

    kwargs = {}

    if model.llm_is_thinking_model:
        thinking_budget = ReasoningEffort.high.thinking_budget
        if model.name.startswith("o"):
            # o-series models dont support reasoning_effort
            reasoning_effort = None
        if reasoning_effort:
            re = ReasoningEffort.from_api(reasoning_effort)
            if re == ReasoningEffort.minimal:  # deprecated
                re = ReasoningEffort.low
            if "gemini" in model.name and model.version < 3:
                thinking_budget = re.thinking_budget
                kwargs["extra_body"] = {
                    "google": {
                        "thinking_config": {
                            "thinking_budget": thinking_budget,
                        },
                    }
                }
            elif "claude" in model.name:
                # claude requires thinking blocks from previous turns for tool calls, which we don't have
                if not any(entry.get("role") == "tool" for entry in messages):
                    thinking_budget = re.thinking_budget
                    kwargs["extra_body"] = {
                        "thinking": {
                            "type": "enabled",
                            "budget_tokens": thinking_budget,
                        }
                    }
                    # claude doesn't support temperature if thinking is enabled
                    temperature = None
            else:
                kwargs["reasoning_effort"] = re.name
        # add some extra tokens for thinking
        max_tokens = max(thinking_budget + 1000, max_tokens)

    if model.llm_max_output_tokens:
        # cap the max tokens at the model's max limit
        max_tokens = min(max_tokens, model.llm_max_output_tokens)

    if "openai" in model.label.lower():
        # openai renamed max_tokens to max_completion_tokens
        kwargs["max_completion_tokens"] = max_tokens
    else:
        kwargs["max_tokens"] = max_tokens

    if "openai" in model.label.lower() and model.llm_is_thinking_model:
        # openai thinking models don't support frequency_penalty and presence_penalty
        avoid_repetition = False

    if model.name in ["apertus_70b_instruct", "sea_lion_v4_gemma_3_27b_it"]:
        # Swiss AI Apertus model doesn't support tool calling
        tools = None

    if avoid_repetition:
        kwargs["frequency_penalty"] = 0.1
        kwargs["presence_penalty"] = 0.25

    if tools:
        kwargs["tools"] = [tool.spec_openai for tool in tools]

    if response_format_type:
        kwargs["response_format"] = {"type": response_format_type}

    if temperature is not None:
        kwargs["temperature"] = temperature

    model_ids = model.model_id
    if isinstance(model_ids, str):
        model_ids = [model_ids]

    with capture_openai_content_policy_violation():
        completion, used_model = try_all(
            *[
                _get_chat_completions_create(
                    model=model_id,
                    api_key=model.api_key,
                    base_url=model.base_url,
                    messages=messages,
                    stop=stop or NOT_GIVEN,
                    n=num_outputs,
                    stream=stream,
                    **kwargs,
                )
                for model_id in model_ids
            ],
        )
        if stream:
            return _stream_openai_chunked(
                completion.__stream__(),
                used_model,
                messages,
                start_chunk_size=start_chunk_size,
                stop_chunk_size=stop_chunk_size,
                step_chunk_size=step_chunk_size,
            )

    if not completion or not completion.choices:
        return [format_chat_entry(role=CHATML_ROLE_ASSISTANT, content_text="")]
    else:
        ret = [choice.message.dict() for choice in completion.choices]
        record_openai_llm_usage(used_model, completion, messages, ret)
        return ret


def _get_responses_create(
    model: str, api_key: str | None, base_url: str | None, stream: bool, **kwargs
):
    client = get_openai_client(model, api_key, base_url)

    @wraps(client.responses.create)
    def wrapper():
        # Convert messages format to responses API input format
        messages = kwargs.pop("messages", [])
        input_messages = []
        for msg in messages:
            if msg["role"] == "assistant" and "tool_calls" in msg:
                # function calls
                for tool_call in msg["tool_calls"]:
                    input_messages.append(
                        {
                            "type": "function_call",
                            "call_id": tool_call.get("id", ""),
                            "name": tool_call["function"]["name"],
                            "arguments": tool_call["function"]["arguments"],
                        }
                    )
            elif msg["role"] == "tool":
                # function call output
                input_messages.append(
                    {
                        "type": "function_call_output",
                        "call_id": msg["tool_call_id"],
                        "output": msg["content"],
                    }
                )
            else:
                input_messages.append({"role": msg["role"], "content": msg["content"]})

        response = client.responses.create(
            model=model, input=input_messages, stream=stream, **kwargs
        )
        return response, model

    return wrapper


def _get_chat_completions_create(
    model: str, api_key: str | None, base_url: str | None, **kwargs
):
    client = get_openai_client(model, api_key, base_url)

    @wraps(client.chat.completions.create)
    def wrapper():
        # logger.debug(f"{model=} {kwargs=}")
        return client.chat.completions.create(model=model, **kwargs), model

    return wrapper


def _stream_openai_chunked(
    r: typing.Iterable[ChatCompletionChunk],
    used_model: str,
    messages: list[ConversationEntry],
    *,
    start_chunk_size: int,
    stop_chunk_size: int,
    step_chunk_size: int,
) -> typing.Generator[list[ConversationEntry], None, None]:
    ret = []
    chunk_size = start_chunk_size

    completion_chunk = None
    for completion_chunk in r:
        if not completion_chunk.choices:
            # not a valid completion chunk...
            # anthropic sends pings like this that must be ignored
            continue

        changed = False

        for choice in completion_chunk.choices:
            delta = choice.delta
            if not delta:
                continue

            try:
                # get the entry for this choice
                entry = ret[choice.index]
            except IndexError:
                # initialize the entry
                entry = dict(role=delta.role, content="", chunk="")
                ret.append(entry)
            # this is to mark the end of streaming
            entry["finish_reason"] = choice.finish_reason

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    try:
                        tc = entry["tool_calls"][tc_delta.index]
                    except (KeyError, IndexError):
                        tc = tc_delta.model_dump()
                        entry.setdefault("tool_calls", []).append(tc)
                    else:
                        if tc["function"]["arguments"] is None:
                            tc["function"]["arguments"] = ""
                        tc["function"]["arguments"] += tc_delta.function.arguments

            if delta.content:
                # append the delta to the current chunk
                entry["chunk"] += delta.content
                changed = is_llm_chunk_large_enough(entry, chunk_size)
            elif entry["chunk"]:
                # content stream has ended, stream the chunk
                entry["content"] += entry["chunk"]
                entry["chunk"] = ""
                changed = True

        if changed:
            # increase the chunk size, but don't go over the max
            chunk_size = min(chunk_size + step_chunk_size, stop_chunk_size)
            # stream the chunk
            yield ret

    # add the leftover chunks
    for entry in ret:
        entry["content"] += entry["chunk"]
    yield ret

    if not completion_chunk:
        return
    record_openai_llm_usage(used_model, completion_chunk, messages, ret)


def _stream_openai_responses(
    r: typing.Iterable[ResponseStreamEvent],
    used_model: str,
    messages: list[ConversationEntry],
    *,
    start_chunk_size: int,
    stop_chunk_size: int,
    step_chunk_size: int,
) -> typing.Generator[list[ConversationEntry], None, None]:
    entry: ConversationEntry = dict(role="assistant", content="", chunk="", metrics={})
    ret = [entry]
    chunk_size = start_chunk_size
    thinking_started_at = time()

    for event in r:
        if (
            event.type == "response.output_item.added"
            and event.item.type == "reasoning"
        ):
            thinking_started_at = time()
            entry["chunk"] += "<think>\n\n"
        elif event.type == "response.reasoning_summary_part.done":
            entry["chunk"] += "\n\n"
        elif (
            event.type == "response.output_item.done" and event.item.type == "reasoning"
        ):
            entry["chunk"] += "</think>\n\n"
            entry["metrics"]["thinking_duration_sec"] = round(
                time() - thinking_started_at
            )

        # Handle different event types from Responses API
        if event.type in [
            "response.output_text.delta",
            "response.reasoning_summary_text.delta",
        ]:
            entry["chunk"] += event.delta
            if is_llm_chunk_large_enough(entry, chunk_size):
                # increase the chunk size, but don't go over the max
                chunk_size = min(chunk_size + step_chunk_size, stop_chunk_size)
                # stream the chunk
                yield ret

        elif event.type == "response.output_text.done":
            # content stream has ended, stream the chunk immediately
            entry["content"] += entry["chunk"]
            entry["chunk"] = ""
            yield ret

        elif (
            event.type in ["response.output_item.added", "response.output_item.done"]
            and event.item.type == "function_call"
        ):
            tool_calls = entry.setdefault("tool_calls", [])
            new_tc = {
                "id": event.item.call_id,
                "type": "function",
                "function": {
                    "name": event.item.name,
                    "arguments": event.item.arguments,
                },
            }
            for tc in tool_calls:
                if tc["id"] == new_tc["id"]:
                    tc.update(new_tc)
                    break
            else:
                tool_calls.append(new_tc)
            yield ret

        if isinstance(event, ResponseCompletedEvent):
            record_openai_llm_usage(used_model, event.response, messages, ret)

    # add the leftover chunks
    for entry in ret:
        entry["content"] += entry["chunk"]
    yield ret


def is_llm_chunk_large_enough(entry: dict, chunk_size: int) -> bool:
    from pyquery import PyQuery as pq

    # if the chunk is too small, we need to wait for more data
    chunk = entry["chunk"]
    if len(chunk) < chunk_size:
        return False

    # if chunk contains buttons we wait for the buttons to be complete
    if "<button" in chunk:
        doc = pq(f"<root>{chunk}</root>")
        if doc("button"):
            last_part = doc.contents()[-1]
            # if the last part is not a string or is empty, we need to wait for more data
            if not (isinstance(last_part, str) and last_part.strip()):
                return False

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
        # we found a separator, so we can stop looking and yield the partial result
        return True

    return False


def record_openai_llm_usage(
    model: str,
    completion: ChatCompletion | ChatCompletionChunk | Response,
    messages: list[ConversationEntry],
    choices: list[ConversationEntry],
):
    from usage_costs.cost_utils import record_cost_auto
    from usage_costs.models import ModelSku

    if isinstance(completion.usage, CompletionUsage):
        prompt_tokens = completion.usage.prompt_tokens
        completion_tokens = completion.usage.completion_tokens or (
            completion.usage.completion_tokens_details
            and completion.usage.completion_tokens_details.reasoning_tokens
        )
    elif isinstance(completion.usage, ResponseUsage):
        prompt_tokens = completion.usage.input_tokens
        completion_tokens = completion.usage.output_tokens
    else:
        prompt_tokens = sum(
            default_length_function(get_entry_text(entry), model=completion.model)
            for entry in messages
        )
        completion_tokens = sum(
            default_length_function(get_entry_text(entry), model=completion.model)
            for entry in choices
        )

    if prompt_tokens:
        record_cost_auto(
            model=model,
            sku=ModelSku.llm_prompt,
            quantity=prompt_tokens,
        )
    if completion_tokens:
        record_cost_auto(
            model=model,
            sku=ModelSku.llm_completion,
            quantity=completion_tokens,
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


def get_openai_client(
    model: str, api_key: str | None = None, base_url: str | None = None
):
    import openai

    if base_url:
        client = openai.OpenAI(
            api_key=api_key or settings.OPENAI_API_KEY,
            max_retries=0,
            base_url=base_url,
        )
    elif model.startswith(AZURE_OPENAI_MODEL_PREFIX) and "-ca-" in model:
        client = openai.AzureOpenAI(
            api_key=settings.AZURE_OPENAI_KEY_CA,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT_CA,
            api_version="2024-12-01-preview",
            max_retries=0,
        )
    elif model.startswith(AZURE_OPENAI_MODEL_PREFIX) and "-eastus2-" in model:
        client = openai.AzureOpenAI(
            api_key=settings.AZURE_OPENAI_KEY_EASTUS2,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT_EASTUS2,
            api_version="2024-12-01-preview",
            max_retries=0,
        )
    elif model.startswith("sarvam-"):
        client = openai.OpenAI(
            api_key=settings.SARVAM_API_KEY,
            max_retries=0,
            base_url="https://api.sarvam.ai/v1",
        )
    elif model.startswith("claude-"):
        client = openai.OpenAI(
            api_key=settings.ANTHROPIC_API_KEY,
            max_retries=0,
            base_url="https://api.anthropic.com/v1",
        )
    elif model.startswith("google/"):
        client = openai.OpenAI(
            api_key=get_google_auth_token(),
            max_retries=0,
            base_url=f"https://aiplatform.googleapis.com/v1/projects/{settings.GCP_PROJECT}/locations/{settings.GCP_REGION}/endpoints/openapi",
        )
    elif model.startswith("aisingapore/"):
        client = openai.OpenAI(
            api_key=settings.SEA_LION_API_KEY,
            max_retries=0,
            base_url="https://api.sea-lion.ai/v1",
        )
    elif model.startswith("swiss-ai/"):
        client = openai.OpenAI(
            api_key=settings.PUBLICAI_API_KEY,
            max_retries=0,
            base_url="https://api.publicai.co/v1",
            default_headers={"User-Agent": "gooey/openai-sdk"},
        )
    elif model.startswith("AI71ai/"):
        import modal
        from modal_functions.agri_llm import app

        modal_fn = modal.Function.from_name(app.name, "serve")
        client = openai.OpenAI(
            api_key=settings.MODAL_VLLM_API_KEY,
            max_retries=0,
            base_url=str(furl(modal_fn.get_web_url()) / "v1"),
        )
    else:
        client = openai.OpenAI(
            api_key=settings.OPENAI_API_KEY,
            max_retries=0,
        )
    return client


@aifail.retry_if(aifail.http_should_retry)
def _run_groq_chat(
    *,
    model: str,
    messages: list[ConversationEntry],
    max_tokens: int,
    tools: list[BaseLLMTool] | None,
    temperature: float,
    stop: list[str] | None,
    response_format_type: ResponseFormatType | None,
    avoid_repetition: bool = False,
):
    from usage_costs.cost_utils import record_cost_auto
    from usage_costs.models import ModelSku

    data = dict(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    if tools:
        data["tools"] = [tool.spec_openai for tool in tools]
    if stop:
        data["stop"] = stop
    if response_format_type:
        data["response_format"] = {"type": response_format_type}
    if avoid_repetition:
        data["frequency_penalty"] = 0.1
        data["presence_penalty"] = 0.25
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
        json=data,
    )
    raise_for_status(r)
    out = r.json()

    record_cost_auto(
        model=model, sku=ModelSku.llm_prompt, quantity=out["usage"]["prompt_tokens"]
    )
    record_cost_auto(
        model=model,
        sku=ModelSku.llm_completion,
        quantity=out["usage"]["completion_tokens"],
    )
    return [choice["message"] for choice in out["choices"]]


@retry_if(aifail.http_should_retry)
def _run_fireworks_chat(
    *,
    model: str,
    messages: list[ConversationEntry],
    max_tokens: int,
    num_outputs: int,
    temperature: float | None = None,
    stop: list[str] | None = None,
    avoid_repetition: bool = False,
    tools: list[BaseLLMTool] | None = None,
    response_format_type: ResponseFormatType | None = None,
):
    from usage_costs.cost_utils import record_cost_auto
    from usage_costs.models import ModelSku

    data = dict(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        n=num_outputs,
        temperature=temperature,
    )
    if tools:
        data["tools"] = [tool.spec_openai for tool in tools]
    if avoid_repetition:
        data["frequency_penalty"] = 0.1
        data["presence_penalty"] = 0.25
    if stop:
        data["stop"] = stop
    if response_format_type:
        data["response_format"] = {"type": response_format_type}
    r = requests.post(
        "https://api.fireworks.ai/inference/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.FIREWORKS_API_KEY}"},
        json=data,
    )
    raise_for_status(r)
    out = r.json()

    record_cost_auto(
        model=model,
        sku=ModelSku.llm_prompt,
        quantity=out["usage"]["prompt_tokens"],
    )
    record_cost_auto(
        model=model,
        sku=ModelSku.llm_completion,
        quantity=out["usage"]["completion_tokens"],
    )
    return [choice["message"] for choice in out["choices"]]


@retry_if(aifail.http_should_retry)
def _run_mistral_chat(
    *,
    model: str,
    messages: list[ConversationEntry],
    max_tokens: int,
    num_outputs: int,
    temperature: float | None = None,
    stop: list[str] | None = None,
    avoid_repetition: bool = False,
    tools: list[BaseLLMTool] | None = None,
    response_format_type: ResponseFormatType | None = None,
):
    from usage_costs.cost_utils import record_cost_auto
    from usage_costs.models import ModelSku

    data = dict(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        n=num_outputs,
        temperature=temperature,
    )
    if tools:
        data["tools"] = [tool.spec_openai for tool in tools]
    if avoid_repetition:
        data["frequency_penalty"] = 0.1
        data["presence_penalty"] = 0.25
    if stop:
        data["stop"] = stop
    if response_format_type:
        data["response_format"] = {"type": response_format_type}
    r = requests.post(
        "https://api.mistral.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.MISTRAL_API_KEY}"},
        json=data,
    )
    raise_for_status(r)
    out = r.json()
    record_cost_auto(
        model=model,
        sku=ModelSku.llm_prompt,
        quantity=out["usage"]["prompt_tokens"],
    )
    record_cost_auto(
        model=model,
        sku=ModelSku.llm_completion,
        quantity=out["usage"]["completion_tokens"],
    )
    return list(_parse_mistral_output(out))


def _parse_mistral_output(out: dict) -> typing.Iterable[dict]:
    for choice in out["choices"]:
        message = choice["message"]
        content = message.get("content")
        # clean up the damn references
        if isinstance(content, list):
            message["content"] = "".join(
                filter(None, map(_mistral_ref_chunk_to_str, content))
            )
        else:
            message["content"] = content.replace("[REF]", " [").replace("[/REF]", "]")
        yield message


def _mistral_ref_chunk_to_str(chunk: dict) -> str | None:
    text = chunk.get("text")
    if text:
        return text
    ref_ids = chunk.get("reference_ids")
    if ref_ids:
        return " [" + ", ".join(map(str, ref_ids)) + "]"
    return None


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
    response_format_type: ResponseFormatType | None,
):
    contents = []
    for entry in messages:
        contents.append(
            {
                "role": gemini_role_map[entry["role"]],
                "parts": [
                    {"text": get_entry_text(entry)},
                ]
                + [
                    {
                        "fileData": {
                            "mimeType": mimetypes.guess_type(image)[0] or "image/png",
                            "fileUri": gs_url_to_uri(image),
                        },
                    }
                    for image in get_entry_images(entry)
                ],
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
        response_format_type=response_format_type,
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
    stop: list[str] | None = None,
    response_format_type: ResponseFormatType | None = None,
) -> str:
    session, project = get_google_auth_session()
    generation_config = {
        "temperature": temperature,
        "maxOutputTokens": max_output_tokens,
        "stopSequences": stop or [],
    }
    if response_format_type == "json_object":
        generation_config["response_mime_type"] = "application/json"
    r = session.post(
        f"https://{settings.GCP_REGION}-aiplatform.googleapis.com/v1/projects/{project}/locations/{settings.GCP_REGION}/publishers/google/models/{model_id}:generateContent",
        json={
            "contents": contents,
            "generation_config": generation_config,
        },
    )
    raise_for_status(r)
    ret = "".join(
        parts[0]["text"]
        for msg in r.json()["candidates"]
        if (parts := msg.get("content", {}).get("parts"))
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


def msgs_to_prompt_str(messages: list[ConversationEntry] | dict) -> str:
    return "\n".join(entry_to_prompt_str(entry) for entry in messages)


def entry_to_prompt_str(entry: ConversationEntry) -> str:
    if isinstance(entry, str):
        return entry
    msg = entry.get("role", "") + ": "
    content = get_entry_text(entry).strip()
    if content:
        msg += content
    return msg


def format_chat_entry(
    *,
    role: typing.Literal["system", "user", "assistant", "tool"],
    content_text: str,
    input_images: typing.Optional[list[str]] = None,
    input_audio: typing.Optional[str] = None,
    input_documents: typing.Optional[list[str]] = None,
) -> ConversationEntry:
    text_parts = []
    if input_images:
        text_parts.append(f"Image URLs: {', '.join(input_images)}")
    # if input_audio:
    #     text_parts.append(f"Audio URL: {input_audio}")
    if input_documents:
        text_parts.append(f"Document URLs: {', '.join(input_documents)}")
    text_parts.append(content_text)
    text_with_urls = "\n\n".join(filter(None, text_parts))

    if not input_images and not input_audio:
        return {"role": role, "content": text_with_urls}

    content = []
    if input_images:
        content.extend(
            [{"type": "image_url", "image_url": {"url": url}} for url in input_images]
        )
    if input_audio:
        wavdata, _ = audio_url_to_wav(input_audio)
        audio_data = base64.b64encode(wavdata).decode()
        content.append(
            {
                "type": "input_audio",
                "input_audio": {"data": audio_data, "format": "wav"},
            }
        )
    content.append({"type": "text", "text": text_with_urls})
    return {"role": role, "content": content}


@redis_cache_decorator(ex=3600)  # Cache for 1 hour
def get_google_auth_token():
    from google.auth import default
    import google.auth.transport.requests

    credentials, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(google.auth.transport.requests.Request())
    return credentials.token
