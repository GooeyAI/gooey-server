import jinja2

from daras_ai_v2.language_model import (
    run_language_model,
    model_max_tokens,
    LargeLanguageModels,
)


def generate_final_search_query(
    *,
    request,
    response=None,
    instructions: str,
    context: dict = None,
):
    if context is None:
        context = request.dict()
        if response:
            context |= response.dict()
    query_instructions = jinja2.Template(instructions).render(**context).strip()
    model = LargeLanguageModels[request.selected_model]
    max_tokens = model_max_tokens[model] // 8  # just a sane default
    return run_language_model(
        model=request.selected_model,
        prompt=query_instructions,
        max_tokens=max_tokens,
        quality=request.quality,
        temperature=request.sampling_temperature,
        avoid_repetition=request.avoid_repetition,
    )[0]
