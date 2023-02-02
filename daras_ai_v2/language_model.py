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


class LargeLanguageModels(Enum):
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
                        print(f"({n}/5) captured error, retry in 1s:", repr(e))
                        sleep(retry_delay)
                    else:
                        raise

        return wrapper

    return decorator


@do_retry()
def run_language_model(
    api_provider: str,
    engine: str,
    prompt: str,
    max_tokens: int,
    stop: list[str] | None,
    quality: float,
    num_outputs: int,
    temperature: float,
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

    return [choice["text"] for choice in r["choices"]]
