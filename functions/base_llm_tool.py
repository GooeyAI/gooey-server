from __future__ import annotations

import json
import typing

import gooey_gui as gui

from app_users.models import AppUser
from daras_ai_v2 import icons
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.field_render import field_title_desc
from functions.models import (
    FunctionScopes,
    FunctionTrigger,
)
from widgets.switch_with_section import switch_with_section

if typing.TYPE_CHECKING:
    from bots.models import PublishedRun, SavedRun
    from daras_ai_v2.base import BasePage, JsonTypes
    from functions.workflow_tools import WorkflowLLMTool
    from workspaces.models import Workspace

FUNCTIONS_HELP_TEXT = """\
Functions give your workflow the ability run Javascript code (with webcalls!) \
allowing it execute logic, use common JS libraries or make external API calls \
before or after the workflow runs.
<a href='/functions-help' target='_blank'>Learn more.</a>"""


class BaseLLMTool:
    icon: str = ""
    url: str = ""

    def __init__(
        self,
        name: str,
        label: str,
        description: str,
        properties: dict,
        required: list[str] | None = None,
        await_audio_completed: bool = False,
    ):
        self.name = name
        self.label = label
        self.description = description
        self.properties = properties

        self.spec_parameters = {
            "type": "object",
            "properties": self.properties,
        }
        if required:
            self.spec_parameters["required"] = required

        self.spec_function = {
            "name": name,
            "description": description,
            "parameters": self.spec_parameters,
        }

        ## Yes openai really does have 2 ways to specify tools in their own APIs
        # https://platform.openai.com/docs/api-reference/chat/create
        self.spec_openai = {"type": "function", "function": self.spec_function}
        # https://platform.openai.com/docs/api-reference/realtime-client-events/session/update
        self.spec_openai_audio = {"type": "function"} | self.spec_function
        # https://platform.openai.com/docs/guides/tools?api-mode=responses&tool-type=function-calling
        self.spec_openai_responses = {"type": "function"} | self.spec_function

        self.await_audio_completed = await_audio_completed

    def call_json(self, arguments: str) -> str:
        try:
            kwargs = json.loads(arguments)
            ret = self.call(**kwargs)
        except (json.JSONDecodeError, TypeError) as e:
            ret = dict(error=repr(e))
        return json.dumps(ret)

    def __call__(self, *args, **kwargs) -> typing.Any:
        return self.call(*args, **kwargs)

    def call(self, *args, **kwargs) -> typing.Any:
        raise NotImplementedError

    def get_icon(self) -> str:
        return self.icon

    def get_url(self) -> str:
        return self.url


def get_tool_from_call(
    function_call: dict, tools_by_name: dict[str, "BaseLLMTool"]
) -> tuple[BaseLLMTool, str]:
    name = function_call["name"]
    arguments = function_call["arguments"]
    tool = tools_by_name[name]
    return tool, arguments


def call_recipe_functions(
    *,
    saved_run: SavedRun,
    workspace: Workspace,
    current_user: AppUser,
    request_model: typing.Type[BasePage.RequestModel],
    response_model: typing.Type[BasePage.ResponseModel],
    state: dict,
    trigger: FunctionTrigger,
) -> typing.Iterable[str]:
    tools = list(get_workflow_tools_from_state(state, trigger))
    if not tools:
        return
    yield f"Running {trigger.name} hooks..."
    for tool in tools:
        tool.bind(
            saved_run=saved_run,
            workspace=workspace,
            current_user=current_user,
            request_model=request_model,
            response_model=response_model,
            state=state,
            trigger=trigger,
        )
        tool.call()


def get_workflow_tools_from_state(
    state: dict, trigger: FunctionTrigger
) -> typing.Iterable[WorkflowLLMTool]:
    from functions.workflow_tools import WorkflowLLMTool

    functions = state.get("functions")
    if not functions:
        return
    for function in functions:
        if function.get("trigger") != trigger.name or "/tools/" in function["url"]:
            continue
        yield WorkflowLLMTool(function["url"])


def generate_tool_properties(
    fn_vars: dict, fn_vars_schema: dict
) -> typing.Iterable[tuple[str, dict]]:
    for name, value in fn_vars.items():
        var_schema = fn_vars_schema.get(name, {})
        if var_schema and var_schema.get("role") == "system":
            continue

        json_schema = {"description": var_schema.get("description", "")}
        json_schema |= get_nested_type(value, schema=var_schema)

        yield name, json_schema


def get_nested_type(val, schema=None) -> dict[str, typing.Any]:
    json_type = schema and schema.get("type") or get_json_type(val)
    if json_type == "array":
        try:
            return {"type": "array", "items": get_nested_type(val[0])}
        except (IndexError, TypeError):
            return {"type": "array", "items": {"type": "object"}}
    else:
        return {"type": json_type}


def get_json_type(val) -> "JsonTypes":
    match val:
        case bool():
            return "boolean"
        case str():
            return "string"
        case int() | float() | complex():
            return "number"
        case list() | tuple() | set():
            return "array"
        case _:
            return "object"


def is_functions_enabled(key="functions") -> bool:
    return bool(gui.session_state.get(f"--enable-{key}"))


def functions_input(
    workspace: Workspace | None,
    user: AppUser | None,
    published_run: PublishedRun | None,
    key="functions",
):
    from daras_ai_v2.base import BasePage
    from daras_ai_v2.workflow_url_input import del_button, workflow_url_input
    from recipes.BulkRunner import list_view_editor
    from recipes.Functions import FunctionsPage

    def render_inputs(list_key: str, del_key: str, fn: dict):
        col1, col2 = gui.columns([4, 9], responsive=True)
        url = fn.get("url") or ""
        tool_slug = get_external_tool_slug_from_url(url)
        if tool_slug:
            fn["slug"] = tool_slug
            with col1, gui.styled("& i { width: 28px; }"):
                fn["scope"] = enum_selector(
                    label="",
                    enum_cls=FunctionScopes,
                    format_func=lambda name: FunctionScopes.format_label(
                        name,
                        workspace=workspace,
                        user=user,
                        published_run=published_run,
                    ),
                    key=list_key + ":scope",
                    value=fn.get("scope"),
                    use_selectbox=True,
                )
            with col2:
                with gui.div(className="d-flex align-items-center"):
                    logo = fn.get("logo")
                    if logo:
                        gui.image(
                            logo,
                            style=dict(width="14px", height="14px", marginRight="8px"),
                        )
                    with gui.div(className="flex-grow-1"):
                        gui.write(
                            fn.get("label") or tool_slug,
                            unsafe_allow_html=True,
                            help=(
                                "Embed statically in the prompt with Jinja Template:\n `{{ %s(...) }}`"
                                % tool_slug
                            ),
                        )
                    gui.url_button(url)
                    del_button(del_key)
        else:
            with col1:
                col1.node.props["className"] += " pt-1"
                fn["trigger"] = enum_selector(
                    enum_cls=FunctionTrigger,
                    use_selectbox=True,
                    key=list_key + ":trigger",
                    value=fn.get("trigger"),
                )
            with col2:
                workflow_url_input(
                    page_cls=FunctionsPage,
                    key=list_key + ":url",
                    internal_state=fn,
                    del_key=del_key,
                    current_user=user,
                    include_root=False,
                )
            col2.node.children[0].props["className"] += " col-12"

    def render_section():
        from functions.composio_tools import render_inbuilt_tools_selector

        gui.session_state.setdefault(key, [{}])
        with gui.div(className="d-flex align-items-center gap-3 mb-2"):
            gui.write("###### Functions", help=FUNCTIONS_HELP_TEXT)
            gui.session_state[f"--{key}:add"] = gui.button(
                f"{icons.add} Add",
                type="tertiary",
                className="p-1 mb-2",
                key=f"{key}:add",
            )
            gui.div(className="flex-grow-1")
            render_inbuilt_tools_selector()

        list_view_editor(key=key, render_inputs=render_inputs)

    functions_enabled = switch_with_section(
        f"##### {field_title_desc(BasePage.RequestModel, key)}",
        key=f"--enable-{key}",
        control_keys=[key],
        render_section=render_section,
    )
    if not functions_enabled:
        gui.session_state.pop(key, None)


def render_called_functions(*, saved_run: SavedRun, trigger: FunctionTrigger):
    qs = saved_run.called_functions.filter(trigger=trigger.db_value)
    for called_fn in qs:
        fn_sr = called_fn.function_run
        pr = fn_sr.parent_published_run()
        title = pr and pr.title or "Function"
        with gui.tag(
            "a",
            href=fn_sr.get_app_url(),
            target="_blank",
            className="text-decoration-none d-block mb-2",
        ):
            with gui.div(
                className="border rounded-4 px-3 py-2 d-flex align-items-center justify-content-between bg-light container-margin-reset"
            ):
                gui.write(f"**{trigger.label} -** `{title}`")
                gui.html(icons.external_link)


def get_external_tool_slug_from_url(url: str) -> str | None:
    from daras_ai_v2.fastapi_tricks import resolve_url
    from routers.root import tool_page

    match = resolve_url(url)
    if match and match.route.name == tool_page.__name__:
        tool_slug = match.matched_params["tool_slug"]
        return tool_slug

    return None
