import typing

from pydantic import BaseModel

from daras_ai_v2.language_model import (
    run_language_model,
)
from daras_ai_v2.variables_widget import render_prompt_vars

Model = typing.TypeVar("Model", bound=BaseModel)


def generate_final_search_query(
    *,
    request: Model,
    response: Model = None,
    instructions: str,
    context: dict = None,
    response_format_type: typing.Literal["text", "json_object"] = None,
):
    state = request.model_dict()
    if response:
        state |= response.model_dict()
    if context:
        state |= context
    instructions = render_prompt_vars(instructions, state).strip()
    if not instructions:
        return ""
    return run_language_model(
        model=request.selected_model,
        prompt=instructions,
        max_tokens=request.max_tokens,
        quality=request.quality,
        temperature=request.sampling_temperature,
        avoid_repetition=request.avoid_repetition,
        response_format_type=response_format_type,
    )[0]
