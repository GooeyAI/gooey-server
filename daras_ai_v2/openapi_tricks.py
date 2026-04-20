import asyncio
import typing

from asgiref.sync import sync_to_async
from fastapi import FastAPI
from pydantic import BaseModel

from ai_models.llm_openapi import patch_ai_model_schema_enums


def patch_custom_schema_fastapi(app: FastAPI):
    if getattr(app, "_is_openapi_patched", False):
        return

    app._openapi_old = app.openapi

    def custom_openapi():
        schema = app._openapi_old()
        loop = asyncio.get_running_loop()
        loop.create_task(patch_openapi_schema(schema))
        return schema

    custom_openapi()
    app.openapi = custom_openapi
    app._is_openapi_patched = True


@sync_to_async
def patch_openapi_schema(openapi_schema) -> dict:
    components = openapi_schema.get("components") or {}
    schemas = components.get("schemas") or {}
    patch_ai_model_schema_enums(schemas)
    return schemas


def get_full_pydantic_schema(model: typing.Type[BaseModel]) -> dict:
    schema = model.model_json_schema(ref_template="{model}")
    return inline_pydantic_schema_refs(schema["properties"], schema.get("$defs", {}))


def inline_pydantic_schema_refs(
    schema: dict[str, typing.Any],
    defs: dict[str, typing.Any],
) -> dict[str, typing.Any]:
    if not isinstance(schema, dict):
        return schema

    ref = schema.get("$ref")
    if ref:
        resolved = defs.get(ref, {}).copy()
        if not resolved:
            return schema
        schema.clear()
        schema.update(resolved)

    for key, value in schema.items():
        match value:
            case dict():
                schema[key] = inline_pydantic_schema_refs(value, defs)
            case list():
                schema[key] = [
                    inline_pydantic_schema_refs(item, defs) for item in value
                ]

    return schema
