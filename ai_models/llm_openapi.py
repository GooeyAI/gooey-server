import typing

from pydantic import Field

from ai_models.models import AIModelSpec

_MARKER = "x-gooey-model-marker"

LLMMarker: type[str] = typing.Annotated[
    str,
    Field(json_schema_extra={_MARKER: AIModelSpec.Categories.llm.value}),
]
VideoModelMarker: type[str] = typing.Annotated[
    str,
    Field(json_schema_extra={_MARKER: AIModelSpec.Categories.video.value}),
]
AudioModelMarker: type[str] = typing.Annotated[
    str,
    Field(json_schema_extra={_MARKER: AIModelSpec.Categories.audio.value}),
]


def patch_ai_model_schema_enums(schema, _cache=None):
    _cache = _cache or {}
    match schema:
        case dict():
            category = schema.pop(_MARKER, None)
            if category:
                try:
                    choices = _cache[category]
                except KeyError:
                    _cache[category] = choices = list(
                        AIModelSpec.objects.filter(category=category)
                        .order_for_frontend()
                        .values_list("name", flat=True)
                    )
                schema["enum"] = choices
            for value in schema.values():
                patch_ai_model_schema_enums(value, _cache)
        case list():
            for item in schema:
                patch_ai_model_schema_enums(item, _cache)
