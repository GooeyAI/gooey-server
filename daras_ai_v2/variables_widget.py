import json
import typing
from datetime import datetime
from functools import partial
from types import SimpleNamespace

import gooey_gui as gui
import jinja2
import jinja2.meta
import jinja2.sandbox

from daras_ai_v2 import icons
from functions.recipe_functions import get_json_type

if typing.TYPE_CHECKING:
    from daras_ai_v2.base import JsonTypes


def variables_input(
    *,
    template_keys: typing.Iterable[str],
    label: str = "###### ⌥ Variables",
    description: str = "Variables let you pass custom parameters to your workflow. Access a variable in your instruction prompt with <a href='https://jinja.palletsprojects.com/en/3.1.x/templates/' target='_blank'>Jinja</a>, e.g. `{{ my_variable }}`\n  ",
    key: str = "variables",
    allow_add: bool = False,
    exclude: typing.Iterable[str] = (),
):
    from recipes.BulkRunner import list_view_editor

    variables = gui.session_state.get(key) or {}
    schema_key = key + "_schema"
    variables_schema = gui.session_state.get(schema_key) or {}

    # find all variables in the prompts
    env = jinja2.sandbox.SandboxedEnvironment()
    template_var_names = set()
    error = None
    for k in template_keys:
        try:
            parsed = env.parse(gui.session_state.get(k, ""))
        except jinja2.exceptions.TemplateSyntaxError as e:
            error = e
        else:
            template_var_names |= jinja2.meta.find_undeclared_variables(parsed)

    var_names = (
        (template_var_names | set(variables.keys()))
        - set(context_globals().keys())  # dont show global context variables
        - set(exclude)  # used for hiding request/response fields
    )
    pressed_add = False
    if var_names or allow_add:
        with gui.div(className="d-flex align-items-center gap-3 mb-2"):
            gui.write(
                label,
                help=f"{description} <a href='/variables-help' target='_blank'>Learn more</a>.",
            )
            pressed_add = allow_add and gui.button(
                f"{icons.add} Add", type="tertiary", className="p-1 mb-2"
            )

    list_key = key + ":list"
    list_items = gui.session_state.setdefault(list_key, [])
    var_names -= {item["name"] for item in list_items}
    var_names = sorted(
        var_names, key=lambda x: variables_schema.get(x, {}).get("role") or ""
    )
    for var in var_names:
        list_items.append(
            {
                "name": var,
                "value": variables.get(var),
                "schema": variables_schema.get(var, {}),
            }
        )
    if pressed_add:
        list_items.insert(0, {"name": "", "value": None, "schema": {}, "_edit": True})
    list_items = list_view_editor(
        key=list_key,
        render_inputs=partial(render_list_item, template_var_names=template_var_names),
    )

    if error:
        gui.error(f"{type(error).__qualname__}: {error.message}")

    if not list_items and gui.session_state.get(key) is None:
        return

    gui.session_state[key] = {item["name"]: item["value"] for item in list_items}
    gui.session_state[schema_key] = {
        item["name"]: item["schema"] for item in list_items
    }


def render_list_item(
    entry_key: str, del_key: str, item: dict, *, template_var_names: set
):
    name = item.setdefault("name", "")
    value = item.setdefault("value")

    schema = item.setdefault("schema", {})
    description = schema.get("description")
    value_type = schema.get("type") or get_json_type(value or "")

    is_template_var = name in template_var_names

    dialog_ref = gui.use_alert_dialog(entry_key + ":edit-dialog")
    if gui.session_state.pop(dialog_ref.close_btn_key, None):
        dialog_ref.set_open(False)
    if item.pop("_edit", False) or gui.session_state.pop(dialog_ref.open_btn_key, None):
        dialog_ref.set_open(True)

    if dialog_ref.is_open:
        header, body, footer = gui.modal_scaffold()
        with body:
            if not is_template_var:
                name = item["name"] = gui.text_input(
                    label="###### Name",
                    key=entry_key + ":name",
                    value=name,
                    className="font-monospace",
                )

            description = gui.text_area(
                label="###### Description",
                key=entry_key + ":desc",
                value=description,
            )
            if description:
                schema["description"] = description
            else:
                schema.pop("description", None)
            gui.caption("What is this variable used for?")

            value_type = schema["type"] = gui.radio(
                label="###### Type",
                key=entry_key + ":type",
                options=["string", "number", "boolean", "array", "object"],
                format_func=lambda x: f"{get_type_icon(x)}&nbsp; {x.capitalize()}",
                value=value_type,
            )

            gui.div(className="p-2")

        with header:
            if name:
                gui.write(
                    f'### Edit <code class="fs-3">{name}</code>',
                    unsafe_allow_html=True,
                )
            else:
                gui.write("### Add a Variable")

        with footer:
            with gui.div(className="d-flex justify-content-between w-100"):
                gui.button(
                    label=f"{icons.delete} Delete",
                    key=del_key,
                    className="text-danger danger border-danger",
                )
                gui.button(
                    f"{icons.check} Done",
                    key=dialog_ref.close_btn_key,
                    disabled=not name,
                )

    with gui.div(
        className="d-flex align-items-center gap-4 container-margin-reset mb-2"
    ):
        gui.write(
            f"{get_type_icon(value_type)}&nbsp; **`{name or '?'}`**",
            unsafe_allow_html=True,
        )
        gui.write(f"**{value_type}**", className="text-muted small")

        if schema.get("role") == "system":
            gui.write(
                "System provided",
                help="This variable is automatically provided by the system. ",
                className="text-muted small",
            )
        if is_template_var:
            gui.write(
                "Template variable",
                help="Your instruction or other prompts reference this variable. "
                "Add a value and tap Run to test a sample value.",
                className="text-muted small",
            )

        gui.div(className="flex-grow-1")
        gui.button(
            '<i class="fa-solid fa-pen-to-square"></i>',
            type="link",
            className="mb-0",
            key=dialog_ref.open_btn_key,
        )

    with (
        gui.styled(".gui-input:has(&) { margin-bottom: 0 }")
        if description
        else gui.dummy()
    ):
        item["value"] = json_value_editor(entry_key, value, value_type)

    gui.markdown(description, className="text-muted small")


def json_value_editor(entry_key: str, value, value_type: "JsonTypes"):
    # clear other value types
    for other in ["string", "number", "boolean", "array", "object"]:
        if other != value_type:
            gui.session_state.pop(entry_key + ":" + other, None)
    widget_key = entry_key + ":" + value_type

    match value_type:
        case "string":
            value = gui.text_area(
                label="",
                key=widget_key,
                value=str(value or ""),
                height=100,
            )
        case "number":
            value = gui.number_input(
                label="",
                key=entry_key + ":number",
                value=value,
            )
        case "boolean":
            with gui.div(className="mb-3 inline-radio"):
                selection = gui.radio(
                    label="",
                    key=widget_key,
                    options=["true", "false"],
                    format_func=lambda x: f"`{x}`",
                    value="true" if value else "false",
                )
                value = selection == "true"
        case "array":
            try:
                json_str = json.dumps(value)
            except TypeError:
                json_str = str(value)
            json_str = gui.code_editor(
                label="",
                key=widget_key,
                language="json",
                value=json_str,
                style=dict(maxHeight="300px"),
            )
            try:
                value = json.loads(json_str)
            except json.JSONDecodeError:
                gui.error("Invalid JSON")
            if not isinstance(value, list):
                gui.error("Value must be an array")
        case "object":
            try:
                json_str = json.dumps(value, indent=2)
            except TypeError:
                json_str = str(value)
            json_str = gui.code_editor(
                label="",
                key=widget_key,
                language="json",
                value=json_str,
                style=dict(maxHeight="300px"),
            )
            try:
                value = json.loads(json_str)
            except json.JSONDecodeError:
                gui.error("Invalid JSON")
            if not isinstance(value, dict):
                gui.error("Value must be a JSON object")

    return value


def get_type_icon(value_type: "JsonTypes") -> str:
    match value_type:
        case "string":
            icon = "fa-solid fa-text"
        case "number":
            icon = "fa-solid fa-hashtag"
        case "boolean":
            icon = "fa-solid fa-toggle-on"
        case "array":
            icon = "fa-solid fa-brackets-square"
        case "object":
            icon = "fa-solid fa-brackets-curly"
        case _:
            icon = "fa-solid fa-question"
    return f'<i class="{icon} fa-sm" style="width: 1rem"></i>'


def render_prompt_vars(
    prompt: str, state: dict | None, variables_key: str = "variables"
):
    env = jinja2.sandbox.SandboxedEnvironment()
    state = state.copy()
    variables = state.pop(variables_key, {})
    context = context_globals() | (state or {}) | (variables or {})
    for k, v in context.items():
        if v is None:
            context[k] = ""
        elif isinstance(v, str):
            context[k] = v.strip()
    return env.from_string(prompt).render(**context)


def context_globals():
    return {
        "datetime": SimpleNamespace(
            utcnow=datetime.utcnow().strftime("%B %d, %Y %H:%M:%S %Z"),
        ),
    }
