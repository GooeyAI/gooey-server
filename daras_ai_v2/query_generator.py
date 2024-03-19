import typing

from pydantic import BaseModel

from daras_ai_v2.language_model import (
    run_language_model,
    model_max_tokens,
    LargeLanguageModels,
)
from daras_ai_v2.prompt_vars import render_prompt_vars

Model = typing.TypeVar("Model", bound=BaseModel)


def generate_final_search_query(
    *,
    request: Model,
    response: Model = None,
    instructions: str,
    context: dict = None,
    response_format_type: typing.Literal["text", "json_object"] = None,
):
    if context is None:
        context = request.dict()
        if response:
            context |= response.dict()
    instructions = render_prompt_vars(instructions, context).strip()
    if not instructions:
        return ""
    model = LargeLanguageModels[request.selected_model]
    max_tokens = min(model_max_tokens[model] // 8, 1024)  # just a sane default
    return run_language_model(
        model=request.selected_model,
        prompt=instructions,
        max_tokens=max_tokens,
        quality=request.quality,
        temperature=request.sampling_temperature,
        avoid_repetition=request.avoid_repetition,
        response_format_type=response_format_type,
    )[0]
