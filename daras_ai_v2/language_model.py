import base64
import mimetypes
import re
import typing
from enum import Enum
from functools import wraps

import aifail
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
    ChatCompletion,
)

from daras_ai.image_input import gs_url_to_uri, bytes_to_cv2_img, cv2_img_to_bytes
from daras_ai_v2.asr import get_google_auth_session
from daras_ai_v2.exceptions import raise_for_status, UserError
from daras_ai_v2.gpu_server import call_celery_task
from daras_ai_v2.text_splitter import (
    default_length_function,
    default_separators,
)
from functions.recipe_functions import LLMTools

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


class LLMApis(Enum):
    palm2 = 1
    gemini = 2
    openai = 3
    # together = 4
    groq = 5
    anthropic = 6
    self_hosted = 7


class LLMSpec(typing.NamedTuple):
    label: str
    model_id: str | tuple
    llm_api: LLMApis
    context_window: int
    price: int
    is_chat_model: bool = True
    is_vision_model: bool = False
    is_deprecated: bool = False
    supports_json: bool = False


class LargeLanguageModels(Enum):
    # https://platform.openai.com/docs/models/gpt-4o
    gpt_4_o = LLMSpec(
        label="GPT-4o (openai)",
        model_id=("openai-gpt-4o-prod-eastus2-1", "gpt-4o"),
        llm_api=LLMApis.openai,
        context_window=128_000,
        price=10,
        is_vision_model=True,
        supports_json=True,
    )
    # https://platform.openai.com/docs/models/gpt-4o-mini
    gpt_4_o_mini = LLMSpec(
        label="GPT-4o-mini (openai)",
        model_id="gpt-4o-mini",
        llm_api=LLMApis.openai,
        context_window=128_000,
        price=1,
        is_vision_model=True,
        supports_json=True,
    )
    # https://platform.openai.com/docs/models/gpt-4-turbo-and-gpt-4
    gpt_4_turbo_vision = LLMSpec(
        label="GPT-4 Turbo with Vision (openai)",
        model_id=(
            "openai-gpt-4-turbo-2024-04-09-prod-eastus2-1",
            "gpt-4-turbo-2024-04-09",
        ),
        llm_api=LLMApis.openai,
        context_window=128_000,
        price=6,
        is_vision_model=True,
        supports_json=True,
    )
    gpt_4_vision = LLMSpec(
        label="GPT-4 Vision (openai) 🔻",
        model_id="gpt-4-vision-preview",
        llm_api=LLMApis.openai,
        context_window=128_000,
        price=6,
        is_vision_model=True,
    )

    # https://help.openai.com/en/articles/8555510-gpt-4-turbo
    gpt_4_turbo = LLMSpec(
        label="GPT-4 Turbo (openai)",
        model_id=("openai-gpt-4-turbo-prod-ca-1", "gpt-4-1106-preview"),
        llm_api=LLMApis.openai,
        context_window=128_000,
        price=5,
        supports_json=True,
    )

    # https://platform.openai.com/docs/models/gpt-4
    gpt_4 = LLMSpec(
        label="GPT-4 (openai)",
        model_id=("openai-gpt-4-prod-ca-1", "gpt-4"),
        llm_api=LLMApis.openai,
        context_window=8192,
        price=10,
    )
    gpt_4_32k = LLMSpec(
        label="GPT-4 32K (openai) 🔻",
        model_id="openai-gpt-4-32k-prod-ca-1",
        llm_api=LLMApis.openai,
        context_window=32_768,
        price=20,
    )

    # https://platform.openai.com/docs/models/gpt-3-5
    gpt_3_5_turbo = LLMSpec(
        label="ChatGPT (openai)",
        model_id=("openai-gpt-35-turbo-prod-ca-1", "gpt-3.5-turbo-0613"),
        llm_api=LLMApis.openai,
        context_window=4096,
        price=1,
        supports_json=True,
    )
    gpt_3_5_turbo_16k = LLMSpec(
        label="ChatGPT 16k (openai)",
        model_id=("openai-gpt-35-turbo-16k-prod-ca-1", "gpt-3.5-turbo-16k-0613"),
        llm_api=LLMApis.openai,
        context_window=16_384,
        price=2,
    )
    gpt_3_5_turbo_instruct = LLMSpec(
        label="GPT-3.5 Instruct (openai) 🔻",
        model_id="gpt-3.5-turbo-instruct",
        llm_api=LLMApis.openai,
        context_window=4096,
        price=1,
        is_chat_model=False,
    )

    # https://console.groq.com/docs/models
    llama3_70b = LLMSpec(
        label="Llama 3 70b (Meta AI)",
        model_id="llama3-70b-8192",
        llm_api=LLMApis.groq,
        context_window=8192,
        price=1,
        supports_json=True,
    )
    llama_3_groq_70b_tool_use = LLMSpec(
        label="Llama 3 Groq 70b Tool Use",
        model_id="llama3-groq-70b-8192-tool-use-preview",
        llm_api=LLMApis.groq,
        context_window=8192,
        price=1,
        supports_json=True,
    )
    llama3_8b = LLMSpec(
        label="Llama 3 8b (Meta AI)",
        model_id="llama3-8b-8192",
        llm_api=LLMApis.groq,
        context_window=8192,
        price=1,
        supports_json=True,
    )
    llama_3_groq_8b_tool_use = LLMSpec(
        label="Llama 3 Groq 8b Tool Use",
        model_id="llama3-groq-8b-8192-tool-use-preview",
        llm_api=LLMApis.groq,
        context_window=8192,
        price=1,
        supports_json=True,
    )
    llama2_70b_chat = LLMSpec(
        label="Llama 2 70b Chat [Deprecated] (Meta AI)",
        model_id="llama2-70b-4096",
        llm_api=LLMApis.groq,
        context_window=4096,
        price=1,
        is_deprecated=True,
    )
    mixtral_8x7b_instruct_0_1 = LLMSpec(
        label="Mixtral 8x7b Instruct v0.1 (Mistral)",
        model_id="mixtral-8x7b-32768",
        llm_api=LLMApis.groq,
        context_window=32_768,
        price=1,
        supports_json=True,
    )
    gemma_2_9b_it = LLMSpec(
        label="Gemma 2 9B (Google)",
        model_id="gemma2-9b-it",
        llm_api=LLMApis.groq,
        context_window=8_192,
        price=1,
        supports_json=True,
    )
    gemma_7b_it = LLMSpec(
        label="Gemma 7B (Google)",
        model_id="gemma-7b-it",
        llm_api=LLMApis.groq,
        context_window=8_192,
        price=1,
        supports_json=True,
    )

    # https://cloud.google.com/vertex-ai/docs/generative-ai/learn/models
    gemini_1_5_pro = LLMSpec(
        label="Gemini 1.5 Pro (Google)",
        model_id="gemini-1.5-pro-preview-0409",
        llm_api=LLMApis.gemini,
        context_window=1_000_000,
        price=15,
        is_vision_model=True,
    )
    gemini_1_pro_vision = LLMSpec(
        label="Gemini 1.0 Pro Vision (Google)",
        model_id="gemini-1.0-pro-vision",
        llm_api=LLMApis.gemini,
        context_window=2048,
        price=25,
        is_vision_model=True,
        is_chat_model=False,
    )
    gemini_1_pro = LLMSpec(
        label="Gemini 1.0 Pro (Google)",
        model_id="gemini-1.0-pro",
        llm_api=LLMApis.gemini,
        context_window=8192,
        price=15,
    )
    palm2_chat = LLMSpec(
        label="PaLM 2 Chat (Google)",
        model_id="chat-bison",
        llm_api=LLMApis.palm2,
        context_window=4096,
        price=10,
    )
    palm2_text = LLMSpec(
        label="PaLM 2 Text (Google)",
        model_id="text-bison",
        llm_api=LLMApis.palm2,
        context_window=8192,
        price=15,
        is_chat_model=False,
    )

    # https://docs.anthropic.com/claude/docs/models-overview#model-comparison
    claude_3_5_sonnet = LLMSpec(
        label="Claude 3.5 Sonnet (Anthropic)",
        model_id="claude-3-5-sonnet-20240620",
        llm_api=LLMApis.anthropic,
        context_window=200_000,
        price=15,
        is_vision_model=True,
    )
    claude_3_opus = LLMSpec(
        label="Claude 3 Opus [L] (Anthropic)",
        model_id="claude-3-opus-20240229",
        llm_api=LLMApis.anthropic,
        context_window=200_000,
        price=75,
        is_vision_model=True,
    )
    claude_3_sonnet = LLMSpec(
        label="Claude 3 Sonnet [M] (Anthropic)",
        model_id="claude-3-sonnet-20240229",
        llm_api=LLMApis.anthropic,
        context_window=200_000,
        price=15,
        is_vision_model=True,
    )
    claude_3_haiku = LLMSpec(
        label="Claude 3 Haiku [S] (Anthropic)",
        model_id="claude-3-haiku-20240307",
        llm_api=LLMApis.anthropic,
        context_window=200_000,
        price=2,
        is_vision_model=True,
    )

    sea_lion_7b_instruct = LLMSpec(
        label="SEA-LION-7B-Instruct [Deprecated] (aisingapore)",
        model_id="aisingapore/sea-lion-7b-instruct",
        llm_api=LLMApis.self_hosted,
        context_window=2048,
        price=1,
        is_deprecated=True,
    )
    llama3_8b_cpt_sea_lion_v2_instruct = LLMSpec(
        label="Llama3 8B CPT SEA-LIONv2 Instruct (aisingapore)",
        model_id="aisingapore/llama3-8b-cpt-sea-lionv2-instruct",
        llm_api=LLMApis.self_hosted,
        context_window=8192,
        price=1,
    )
    sarvam_2b = LLMSpec(
        label="Sarvam 2B (sarvamai)",
        model_id="sarvamai/sarvam-2b-v0.5",
        llm_api=LLMApis.self_hosted,
        context_window=2048,
        price=1,
    )

    # https://platform.openai.com/docs/models/gpt-3
    text_davinci_003 = LLMSpec(
        label="GPT-3.5 Davinci-3 [Deprecated] (openai)",
        model_id="text-davinci-003",
        llm_api=LLMApis.openai,
        context_window=4097,
        price=10,
        is_deprecated=True,
    )
    text_davinci_002 = LLMSpec(
        label="GPT-3.5 Davinci-2 [Deprecated] (openai)",
        model_id="text-davinci-002",
        llm_api=LLMApis.openai,
        context_window=4097,
        price=10,
        is_deprecated=True,
    )
    code_davinci_002 = LLMSpec(
        label="Codex [Deprecated] (openai)",
        model_id="code-davinci-002",
        llm_api=LLMApis.openai,
        context_window=8001,
        price=10,
        is_deprecated=True,
    )
    text_curie_001 = LLMSpec(
        label="Curie [Deprecated] (openai)",
        model_id="text-curie-001",
        llm_api=LLMApis.openai,
        context_window=2049,
        price=5,
        is_deprecated=True,
    )
    text_babbage_001 = LLMSpec(
        label="Babbage [Deprecated] (openai)",
        model_id="text-babbage-001",
        llm_api=LLMApis.openai,
        context_window=2049,
        price=2,
        is_deprecated=True,
    )
    text_ada_001 = LLMSpec(
        label="Ada [Deprecated] (openai)",
        model_id="text-ada-001",
        llm_api=LLMApis.openai,
        context_window=2049,
        price=1,
        is_deprecated=True,
    )

    def __init__(self, *args):
        spec = LLMSpec(*args)
        self.spec = spec
        self.model_id = spec.model_id
        self.llm_api = spec.llm_api
        self.context_window = spec.context_window
        self.price = spec.price
        self.is_deprecated = spec.is_deprecated
        self.is_chat_model = spec.is_chat_model
        self.is_vision_model = spec.is_vision_model
        self.supports_json = spec.supports_json

    @property
    def value(self):
        return self.spec.label

    @classmethod
    def _deprecated(cls):
        return {model for model in cls if model.is_deprecated}


def calc_gpt_tokens(
    prompt: str | list[str] | dict | list[dict],
) -> int:
    if isinstance(prompt, (str, dict)):
        messages = [prompt]
    else:
        messages = prompt
    combined = msgs_to_prompt_str(messages)
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
    tools: list[LLMTools] = None,
    stream: bool = False,
    response_format_type: ResponseFormatType = None,
) -> (
    list[str]
    | tuple[list[str], list[list[dict]]]
    | typing.Generator[list[dict], None, None]
):
    assert bool(prompt) != bool(
        messages
    ), "Pleave provide exactly one of { prompt, messages }"

    model: LargeLanguageModels = LargeLanguageModels[str(model)]
    if model.is_chat_model:
        if prompt and not messages:
            # convert text prompt to chat messages
            messages = [
                format_chat_entry(role=CHATML_ROLE_USER, content=prompt),
            ]
        if not model.is_vision_model:
            # remove images from the messages
            messages = [
                format_chat_entry(role=entry["role"], content=get_entry_text(entry))
                for entry in messages
            ]
        if (
            messages
            and response_format_type == "json_object"
            and "JSON" not in str(messages).upper()
        ):
            if messages[0]["role"] != CHATML_ROLE_SYSTEM:
                messages.insert(
                    0,
                    format_chat_entry(
                        role=CHATML_ROLE_SYSTEM, content=DEFAULT_JSON_PROMPT
                    ),
                )
            else:
                messages[0]["content"] = "\n\n".join(
                    [get_entry_text(messages[0]), DEFAULT_JSON_PROMPT]
                )
        entries = _run_chat_model(
            api=model.llm_api,
            model=model.model_id,
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
            return _stream_llm_outputs(entries)
        else:
            return _parse_entries(entries, tools)
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
            api=model.llm_api,
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
                    format_chat_entry(role=CHATML_ROLE_ASSISTANT, content=msg)
                    for msg in ret
                ]
            ]
        return ret


def _stream_llm_outputs(
    result: list | typing.Generator[list[ConversationEntry], None, None],
):
    if isinstance(result, list):  # compatibility with non-streaming apis
        result = [result]
    for entries in result:
        for i, entry in enumerate(entries):
            entries[i]["content"] = entry.get("content") or ""
        yield entries


def _parse_entries(entries: list[dict], tools: list[dict] | None):
    ret = [get_entry_text(entry).strip() for entry in entries]
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
    logger.info(f"{api=} {model=}, {len(prompt)=}, {max_tokens=}, {temperature=}")
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
        case LLMApis.self_hosted:
            return [
                _run_self_hosted_llm(
                    model=model,
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
    api: LLMApis = LLMApis.openai,
    model: str | tuple,
    messages: list[ConversationEntry],
    max_tokens: int,
    num_outputs: int,
    temperature: float,
    stop: list[str] | None,
    avoid_repetition: bool,
    tools: list[LLMTools] | None,
    response_format_type: ResponseFormatType | None,
    stream: bool = False,
) -> list[ConversationEntry] | typing.Generator[list[ConversationEntry], None, None]:
    logger.info(
        f"{api=} {model=}, {len(messages)=}, {max_tokens=}, {temperature=} {stop=} {stream=}"
    )
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
                response_format_type=response_format_type,
                stop=stop,
            )
        case LLMApis.anthropic:
            return _run_anthropic_chat(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=stop,
            )
        case LLMApis.self_hosted:
            return [
                {
                    "role": CHATML_ROLE_ASSISTANT,
                    "content": _run_self_hosted_llm(
                        model=model,
                        text_inputs=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        avoid_repetition=avoid_repetition,
                        stop=stop,
                    ),
                },
            ]
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


def _run_self_hosted_llm(
    *,
    model: str,
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
        and model == LargeLanguageModels.sea_lion_7b_instruct.model_id
    ):
        for i, entry in enumerate(text_inputs):
            if entry["role"] == CHATML_ROLE_SYSTEM:
                text_inputs[i]["role"] = CHATML_ROLE_USER
                text_inputs.insert(i + 1, dict(role=CHATML_ROLE_ASSISTANT, content=""))

    ret = call_celery_task(
        "llm.chat",
        pipeline=dict(
            model_id=model,
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
            model=model,
            sku=ModelSku.llm_prompt,
            quantity=usage["prompt_tokens"],
        )
        record_cost_auto(
            model=model,
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

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_msg,
        messages=anthropic_msgs,
        stop_sequences=stop,
        temperature=temperature,
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

    return [
        {
            "role": CHATML_ROLE_USER,
            "content": "".join(entry.text for entry in response.content),
        }
    ]


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
    response_format_type: ResponseFormatType | None,
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
    completion, used_model = try_all(
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
        return _stream_openai_chunked(completion, used_model, messages)
    if not completion or not completion.choices:
        return [format_chat_entry(role=CHATML_ROLE_ASSISTANT, content="")]
    else:
        ret = [choice.message.dict() for choice in completion.choices]
        record_openai_llm_usage(used_model, completion, messages, ret)
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

    completion_chunk = None
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

    if not completion_chunk:
        return
    record_openai_llm_usage(used_model, completion_chunk, messages, ret)


def record_openai_llm_usage(
    model: str,
    completion: ChatCompletion | ChatCompletionChunk,
    messages: list[ConversationEntry],
    choices: list[ConversationEntry],
):
    from usage_costs.cost_utils import record_cost_auto
    from usage_costs.models import ModelSku

    if completion.usage:
        prompt_tokens = completion.usage.prompt_tokens
        completion_tokens = completion.usage.completion_tokens
    else:
        prompt_tokens = sum(
            default_length_function(get_entry_text(entry), model=completion.model)
            for entry in messages
        )
        completion_tokens = sum(
            default_length_function(get_entry_text(entry), model=completion.model)
            for entry in choices
        )

    record_cost_auto(
        model=model,
        sku=ModelSku.llm_prompt,
        quantity=prompt_tokens,
    )
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


def get_openai_client(model: str):
    import openai

    if model.startswith(AZURE_OPENAI_MODEL_PREFIX) and "-ca-" in model:
        client = openai.AzureOpenAI(
            api_key=settings.AZURE_OPENAI_KEY_CA,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT_CA,
            api_version="2023-10-01-preview",
            max_retries=0,
        )
    elif model.startswith(AZURE_OPENAI_MODEL_PREFIX) and "-eastus2-" in model:
        client = openai.AzureOpenAI(
            api_key=settings.AZURE_OPENAI_KEY_EASTUS2,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT_EASTUS2,
            api_version="2023-10-01-preview",
            max_retries=0,
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
    temperature: float,
    avoid_repetition: bool,
    stop: list[str] | None,
    response_format_type: ResponseFormatType | None,
):
    from usage_costs.cost_utils import record_cost_auto
    from usage_costs.models import ModelSku

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
    if response_format_type:
        data["response_format"] = {"type": response_format_type}
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        json=data,
        headers={
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        },
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
        f"https://{settings.GCP_REGION}-aiplatform.googleapis.com/v1/projects/{project}/locations/{settings.GCP_REGION}/publishers/google/models/{model_id}:generateContent",
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
    *, role: str, content: str, images: list[str] = None
) -> ConversationEntry:
    if images:
        content = [
            {"type": "image_url", "image_url": {"url": url}} for url in images
        ] + [
            {"type": "text", "text": content},
        ]
    return {"role": role, "content": content}
