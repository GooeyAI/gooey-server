import openai
from decouple import config
from transformers import GPT2TokenizerFast

from daras_ai_v2 import settings
from daras_ai_v2.gpu_server import call_gpu_server, GpuEndpoints

GPT3_MAX_ALLOED_TOKENS = 4000

_gpt2_tokenizer = None


def calc_gpt_tokens(text: str) -> int:
    global _gpt2_tokenizer

    if not _gpt2_tokenizer:
        _gpt2_tokenizer = GPT2TokenizerFast.from_pretrained("gpt2")

    return len(_gpt2_tokenizer(text)["input_ids"])


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
        frequency_penalty=0.05 if avoid_repetition else 0,
    )

    # choose the completions that aren't empty
    outputs = []
    for choice in r["choices"]:
        text = choice["text"].strip()
        if text:
            outputs.append(text)
    return outputs
