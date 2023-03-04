import typing
from enum import Enum
from functools import wraps
from time import sleep

import openai
from decouple import config
from openai.error import ServiceUnavailableError, RateLimitError
from transformers import GPT2TokenizerFast

from daras_ai_v2 import settings
from daras_ai_v2.gpu_server import call_gpu_server, GpuEndpoints

GPT3_MAX_ALLOED_TOKENS = 4000

_gpt2_tokenizer = None

openai.api_key = settings.OPENAI_API_KEY
openai.api_base = "https://api.openai.com/v1"


class LargeLanguageModels(Enum):
    gpt_3_5_turbo = "ChatGPT (GPT-3.5-turbo)"
    text_davinci_003 = "Davinci (GPT-3.5)"
    code_davinci_002 = "Code Davinci (Codex)"
    text_curie_001 = "Curie"
    text_babbage_001 = "Babbage"
    text_ada_001 = "Ada"


def calc_gpt_tokens(text: str) -> int:
    global _gpt2_tokenizer

    if not _gpt2_tokenizer:
        _gpt2_tokenizer = GPT2TokenizerFast.from_pretrained("gpt2")

    return len(_gpt2_tokenizer.encode(text, verbose=False))


def do_retry(
    max_retries: int = 5,
    retry_delay: float = 5,
    error_cls=(ServiceUnavailableError, RateLimitError),
):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            n = 0
            while True:
                try:
                    return fn(*args, **kwargs)
                except error_cls as e:
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


@do_retry()
def get_embeddings(
    texts: list[str], engine: str = "text-embedding-ada-002"
) -> list[list[float]]:
    res = openai.Embedding.create(input=texts, engine=engine)
    return [record["embedding"] for record in res["data"]]


class ConversationEntry(typing.TypedDict):
    role: str
    display_name: str | None
    content: str


@do_retry()
def run_chatgpt(
    *,
    # api_provider: str,
    messages: list[dict],
    max_tokens: int,
    # quality: float,
    num_outputs: int,
    temperature: float,
    engine: str = "gpt-3.5-turbo",
    stop: list[str] = None,
    avoid_repetition: bool = False,
) -> list[dict]:
    r = openai.ChatCompletion.create(
        model=engine,
        messages=messages,
        max_tokens=max_tokens,
        stop=stop,
        # best_of=int(num_outputs * quality),
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
    model: LargeLanguageModels,
    prompt: str,
    max_tokens: int,
    quality: float,
    num_outputs: int,
    temperature: float,
    api_provider: str = "openai",
    stop: list[str] = None,
    avoid_repetition: bool = False,
) -> list[str]:
    match api_provider:
        case "openai":
            openai.api_key = settings.OPENAI_API_KEY
            openai.api_base = "https://api.openai.com/v1"
        case "goose.ai":
            openai.api_key = config("GOOSEAI_API_KEY")
            openai.api_base = "https://api.goose.ai/v1"
        case "flan-t5":
            return call_gpu_server(
                endpoint=GpuEndpoints.flan_t5,
                input_data={
                    "prompt": prompt,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "n": num_outputs,
                },
            )

    match model:
        case LargeLanguageModels.gpt_3_5_turbo.name:
            messages = run_chatgpt(
                messages=[
                    {
                        "role": "system",
                        "content": "You are an intelligent AI assistant. Follow the instructions as closely as possible.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                # quality=quality,
                num_outputs=num_outputs,
                temperature=temperature,
                stop=stop,
                avoid_repetition=avoid_repetition,
            )
            return [entry["content"] for entry in messages]
        case LargeLanguageModels.text_davinci_003.name:
            engine = "text-davinci-003"
        case LargeLanguageModels.code_davinci_002.name:
            engine = "code-davinci-002"
        case LargeLanguageModels.text_curie_001.name:
            engine = "text-curie-001"
        case LargeLanguageModels.text_babbage_001.name:
            engine = "text-babbage-001"
        case LargeLanguageModels.text_ada_001.name:
            engine = "text-ada-001"
        case _:
            raise ValueError(f"Unrecognized LLM: {model!r}")

    r = openai.Completion.create(
        engine=engine,
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


CHATML_START_TOKEN = "<|im_start|>"
CHATML_END_TOKEN = "<|im_end|>"

CHATML_ROLE_SYSTEM = "system"
CHATML_ROLE_ASSISSTANT = "assistant"
CHATML_ROLE_USER = "user"


def format_chatml_message(entry: ConversationEntry) -> str:
    msg = CHATML_START_TOKEN + entry["role"]
    content = entry.get("content")
    display_name = entry.get("display_name")
    if display_name:
        pass
    if content:
        msg += "\n" + content + CHATML_END_TOKEN
    return msg
