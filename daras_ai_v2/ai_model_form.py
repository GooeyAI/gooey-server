from __future__ import annotations

import json
import typing
from textwrap import dedent

import gooey_gui as gui

from ai_models.models import AIModelSpec
from daras_ai_v2 import icons
from daras_ai_v2.safety_checker import safety_checker
from daras_ai_v2.variables_widget import render_prompt_vars


def run_prompt_safety_checker(inputs: dict) -> typing.Iterator[str | None]:
    for key in ["prompt", "text_prompt", "negative_prompt"]:
        text = inputs.get(key)
        if not text:
            continue
        inputs[key] = render_prompt_vars(text, gui.session_state)
        yield "Running safety checker..."
        safety_checker(text=text)


def render_fields(
    key: str,
    available_models: dict[str, AIModelSpec],
    selected_models: list[str],
    skip_fields: typing.Iterable[str] = (),
):
    models = list(
        filter(None, (available_models.get(name) for name in selected_models))
    )
    if not models:
        return

    try:
        input_schema = build_combined_input_schema(
            models,
            skip_fields=skip_fields,
        )
    except Exception as e:
        gui.error(f"Error getting input fields: {e}")
        return
    if not input_schema:
        return

    required_fields = set(input_schema.get("required", []))
    ordered_fields = list(input_schema["properties"])
    old_inputs = gui.session_state.get(key) or {}
    new_inputs = {}

    for name in ordered_fields:
        field = input_schema["properties"][name]
        label = field.get("title") or name.title()
        if name in required_fields:
            label = "##### " + label
        value = old_inputs.get(name, field.get("default"))

        value = render_field(
            field=field, name=name, label=label, value=value, key=f"{key}:{name}"
        )
        # leave unset fields out of the payload so the model uses its own default
        if value is not None:
            new_inputs[name] = value

    gui.session_state[key] = new_inputs


def build_combined_input_schema(
    models: typing.Iterable[AIModelSpec],
    skip_fields: typing.Iterable[str] = (),
) -> dict[str, typing.Any] | None:
    model_input_schemas = [
        schema
        for model in models
        if (schema := extract_openapi_schema(model.schema, "request"))
    ]
    if not model_input_schemas:
        return None

    common_fields = set.intersection(
        *(set(schema.get("properties", {})) for schema in model_input_schemas)
    )

    schema = model_input_schemas[0]
    required_fields = set(schema.get("required", []))
    ordered_fields = list(schema.get("x-fal-order-properties") or list(common_fields))
    ordered_fields.sort(key=lambda x: x not in required_fields)

    properties = {}
    required = []
    for name in ordered_fields:
        if name not in common_fields or name in skip_fields:
            continue
        properties[name] = schema["properties"][name]
        if name in required_fields:
            required.append(name)

    ret = {"type": "object", "properties": properties}
    if required:
        ret["required"] = required
    return ret


def render_field(*, field: dict, name: str, label: str, value: typing.Any, key: str):
    description = field.get("description")
    if description:
        help_text = dedent(description)
    else:
        help_text = None
    default = field.get("default")
    field = resolve_field_anyof(field)
    match field["type"]:
        case ("string" | "integer" | "number") as _type if field.get("enum"):
            selected_value = gui.selectbox(
                label=label, value=value, help=help_text, options=field["enum"]
            )
            pytype = {"string": str, "integer": int, "number": float}[_type]
            return pytype(selected_value)
        case "array" if "lora" in name or "url" in name:
            return gui.file_uploader(
                label=label,
                value=value,
                help=help_text,
                accept_multiple_files=True,
            )
        case "string" if "lora" in name or "url" in name:
            return gui.file_uploader(
                label=label,
                value=value,
                help=help_text,
            )
        case "string":
            return gui.text_area(label=label, value=value, help=help_text)
        case "integer":
            minimum = field.get("minimum")
            maximum = field.get("maximum")
            if minimum is not None and maximum is not None:
                return render_slider_with_erase(
                    key=key,
                    label=label,
                    value=value,
                    help_text=help_text,
                    minimum=minimum,
                    maximum=maximum,
                    default=default,
                )
            return gui.number_input(
                label=label,
                value=value,
                help=help_text,
                min_value=minimum,
                max_value=maximum,
                step=1,
            )
        case "number":
            return gui.number_input(
                label=label,
                value=value,
                help=help_text,
                min_value=field.get("minimum"),
                max_value=field.get("maximum"),
                step=0.1,
            )
        case "boolean":
            return gui.checkbox(label=label, value=value, help=help_text)
        case "object":
            try:
                json_str = json.dumps(value, indent=2)
            except TypeError:
                json_str = str(value)
            json_str = gui.code_editor(
                label="",
                language="json",
                value=json_str,
                style=dict(maxHeight="300px"),
            )
            try:
                parsed_value = json.loads(json_str)
            except json.JSONDecodeError:
                gui.error("Invalid JSON")
                return None
            if not isinstance(parsed_value, dict):
                gui.error("Value must be a JSON object")
                return None
            return parsed_value


def render_slider_with_erase(
    *,
    key: str,
    label: str,
    value: int | None,
    help_text: str | None,
    minimum: int,
    maximum: int,
    default: int | None,
) -> int | None:
    slider_key = f"__ai_model_field:{key}"
    # a range input can't be empty, so a field with no default is unset while
    # its slider is parked at the start
    unset_at_minimum = default is None
    if default is None:
        default = minimum
    if value is None:
        value = default
    is_unset = unset_at_minimum and gui.session_state.get(slider_key, value) == minimum
    if is_unset:
        label += " _(not set)_"

    with gui.div(className="d-flex align-items-end gap-2"):
        with gui.div(className="flex-grow-1"):
            ret = gui.slider(
                label=label,
                min_value=minimum,
                max_value=maximum,
                value=value,
                step=1,
                key=slider_key,
                help=help_text,
            )
        pressed_erase = gui.button(
            icons.erase,
            key=slider_key + ":erase",
            type="tertiary",
            title="Reset to default",
            # vertically center the button with the slider's input row
            style=dict(marginBottom="0.65rem"),
            disabled=ret == default,
        )

    if pressed_erase:
        gui.session_state[slider_key] = default
        gui.rerun()
    if is_unset:
        return None
    return ret


def resolve_field_anyof(field: dict) -> dict:
    if field.get("type"):
        return field
    for props in field.get("anyOf", []):
        inner_type = props.get("type")
        if inner_type and inner_type != "null":
            return props
    return {"type": "object"}


def extract_openapi_schema(
    openapi_json: dict, schema_type: typing.Literal["request", "response"]
) -> dict | None:
    if openapi_json.get("properties"):
        return openapi_json

    endpoint_id = (
        openapi_json.get("info", {}).get("x-fal-metadata", {}).get("endpointId")
    )

    paths = openapi_json.get("paths", {})

    if schema_type == "request":
        path_key = f"/{endpoint_id}"
        method_data = paths.get(path_key, {}).get("post", {})
        schema_ref = (
            method_data.get("requestBody", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
            .get("$ref")
        )
    else:  # output
        path_key = f"/{endpoint_id}/requests/{{request_id}}"
        method_data = paths.get(path_key, {}).get("get", {})
        schema_ref = (
            method_data.get("responses", {})
            .get("200", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
            .get("$ref")
        )

    if not schema_ref:
        return {}

    schema_name = schema_ref.split("/")[-1]
    return openapi_json.get("components", {}).get("schemas", {}).get(schema_name, {})


def get_url_from_result(result: dict | list | str | None) -> str | None:
    if not result:
        return None
    match result:
        case list():
            return get_url_from_result(result[0])
        case dict():
            return result.get("url")
        case _:
            return result
