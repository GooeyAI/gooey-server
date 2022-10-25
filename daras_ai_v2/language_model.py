import openai
from decouple import config


def run_language_model(
    api_provider: str,
    engine: str,
    prompt: str,
    max_tokens: int,
    stop: list[str] | None,
    quality: float,
    num_outputs: int,
    temperature: float,
):
    match api_provider:
        case "openai":
            openai.api_key = config("OPENAI_API_KEY")
            openai.api_base = "https://api.openai.com/v1"
        case "goose.ai":
            openai.api_key = config("GOOSEAI_API_KEY")
            openai.api_base = "https://api.goose.ai/v1"

    r = openai.Completion.create(
        engine=engine,
        prompt=prompt,
        max_tokens=max_tokens,
        stop=stop,
        best_of=int(num_outputs * quality),
        n=num_outputs,
        temperature=temperature,
    )

    # choose the completions that aren't empty
    outputs = []
    for choice in r["choices"]:
        text = choice["text"].strip()
        if text:
            outputs.append(text)
    return outputs
