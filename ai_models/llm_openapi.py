import typing

from pydantic import Field

from ai_models.models import AIModelSpec

_LLM_MODEL_MARKER = "x-gooey-llm-model"

LLMModelField = typing.Annotated[
    str,
    Field(json_schema_extra={_LLM_MODEL_MARKER: True}),
]


def patch_llm_model_schema_enums(
    schema: dict | list[typing.Any], llm_model_names: list[str] | None = None
) -> None:
    match schema:
        case dict():
            if schema.pop(_LLM_MODEL_MARKER, None):
                if llm_model_names is None:
                    llm_model_names = list(
                        AIModelSpec.objects.get_llms_for_frontend().values_list(
                            "name", flat=True
                        )
                    )
                schema["enum"] = llm_model_names
            for value in schema.values():
                patch_llm_model_schema_enums(value, llm_model_names)
        case list():
            for item in schema:
                patch_llm_model_schema_enums(item, llm_model_names)
