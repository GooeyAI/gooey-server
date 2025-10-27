from __future__ import annotations

import json
import typing

import gooey_gui as gui
from django.utils.text import slugify

from app_users.models import AppUser
from daras_ai_v2 import icons
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.field_render import field_title_desc
from daras_ai_v2.settings import templates
from functions.models import CalledFunction, FunctionTrigger
from widgets.switch_with_section import switch_with_section

if typing.TYPE_CHECKING:
    from bots.models import SavedRun
    from daras_ai_v2.base import BasePage, JsonTypes
    from workspaces.models import Workspace

FUNCTIONS_HELP_TEXT = """\
Functions give your workflow the ability run Javascript code (with webcalls!) \
allowing it execute logic, use common JS libraries or make external API calls \
before or after the workflow runs.
<a href='/functions-help' target='_blank'>Learn more.</a>"""


class BaseLLMTool:
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

        self.await_audio_completed = await_audio_completed

    def call_json(self, arguments: str) -> str:
        try:
            kwargs = json.loads(arguments)
            ret = self.call(**kwargs)
        except (json.JSONDecodeError, TypeError) as e:
            ret = dict(error=repr(e))
        return json.dumps(ret)

    def call(self, **kwargs) -> typing.Any:
        raise NotImplementedError


class WorkflowLLMTool(BaseLLMTool):
    """External function tool that calls workflow URLs."""

    def __init__(self, function_url: str):
        from bots.models import Workflow
        from daras_ai_v2.workflow_url_input import url_to_runs

        self.function_url = function_url

        self.page_cls, self.fn_sr, self.fn_pr = url_to_runs(function_url)
        self._fn_runs = (self.fn_sr, self.fn_pr)

        self.is_function_workflow = self.fn_sr.workflow == Workflow.FUNCTIONS
        if self.is_function_workflow:
            fn_vars = self.fn_sr.state.get("variables", {})
            fn_vars_schema = self.fn_sr.state.get("variables_schema", {})
        else:
            fn_vars = self.page_cls.get_example_request(self.fn_sr.state, self.fn_pr)[1]
            fn_vars_schema = self.page_cls.RequestModel.model_json_schema().get(
                "properties", {}
            )
        properties = dict(generate_tool_properties(fn_vars, fn_vars_schema))

        name = slugify(self.fn_pr.title).replace("-", "_")
        super().__init__(
            name=name,
            label=self.fn_pr.title or name,
            description=self.fn_pr.notes,
            properties=properties,
        )

    def bind(
        self,
        saved_run: SavedRun,
        workspace: Workspace,
        current_user: AppUser,
        request_model: typing.Type[BasePage.RequestModel],
        response_model: typing.Type[BasePage.ResponseModel],
        state: dict,
        trigger: FunctionTrigger,
    ) -> "WorkflowLLMTool":
        self.saved_run = saved_run
        self.workspace = workspace
        self.current_user = current_user
        self.request_model = request_model
        self.response_model = response_model
        self.state = state
        self.trigger = trigger
        return self

    def call(self, **kwargs):
        from bots.models import Workflow
        from daras_ai_v2.base import extract_model_fields

        try:
            self.saved_run
        except AttributeError:
            raise RuntimeError(f"This {self.__class__} instance is not yet bound")

        fn_sr, fn_pr = self._fn_runs

        if fn_sr.workflow == Workflow.FUNCTIONS:
            state_vars = self.state.setdefault("variables", {})
            state_vars_schema = self.state.setdefault("variables_schema", {})
            system_vars, system_vars_schema = self._get_system_vars()
            request_body = dict(
                variables=(
                    (fn_sr.state.get("variables") or {})
                    | state_vars
                    | system_vars
                    | kwargs
                ),
                variables_schema=(
                    (fn_sr.state.get("variables_schema") or {})
                    | state_vars_schema
                    | system_vars_schema
                ),
            )
        else:
            request_body = kwargs

        result, fn_sr = fn_sr.submit_api_call(
            workspace=self.workspace,
            current_user=self.current_user,
            parent_pr=fn_pr,
            request_body=request_body,
            deduct_credits=False,
        )

        CalledFunction.objects.create(
            saved_run=self.saved_run,
            function_run=fn_sr,
            trigger=self.trigger.db_value,
        )

        # wait for the result if its a pre request function
        if self.trigger == FunctionTrigger.post:
            return
        fn_sr.wait_for_celery_result(result)
        # if failed, raise error
        if fn_sr.error_msg:
            raise RuntimeError(fn_sr.error_msg)

        if fn_sr.workflow != Workflow.FUNCTIONS:
            page_cls = Workflow(fn_sr.workflow).page_cls
            return_value = extract_model_fields(page_cls.ResponseModel, fn_sr.state)
            return return_value

        # save the output from the function
        return_value = fn_sr.state.get("return_value")
        if return_value is not None:
            if isinstance(return_value, dict):
                for k, v in return_value.items():
                    if (
                        k in self.request_model.model_fields
                        or k in self.response_model.model_fields
                    ):
                        self.state[k] = v
                    else:
                        state_vars[k] = v
                        state_vars_schema[k] = {"role": "system"}
            else:
                state_vars["return_value"] = return_value
                state_vars_schema["return_value"] = {"role": "system"}

        return dict(
            return_value=return_value,
            error=fn_sr.state.get("error"),
            logs=fn_sr.state.get("logs"),
        )

    def _get_system_vars(self) -> tuple[dict, dict]:
        request = self.request_model.model_validate(self.state)
        system_vars = dict(
            web_url=self.saved_run.get_app_url(),
            request=request.model_dump(
                exclude_unset=True, exclude={"variables"}, mode="json"
            ),
            response={
                k: v
                for k, v in self.state.items()
                if k in self.response_model.model_fields
            },
        )
        system_vars_schema = {var: {"role": "system"} for var in system_vars}

        return system_vars, system_vars_schema


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
        except IndexError:
            return {"type": "array", "items": {"type": "object"}}
    else:
        return {"type": json_type}


def get_json_type(val) -> "JsonTypes":
    match val:
        case str():
            return "string"
        case int() | float() | complex():
            return "number"
        case bool():
            return "boolean"
        case list() | tuple() | set():
            return "array"
        case _:
            return "object"


def is_functions_enabled(key="functions") -> bool:
    return bool(gui.session_state.get(f"--enable-{key}"))


def functions_input(current_user: AppUser, key="functions"):
    from daras_ai_v2.base import BasePage
    from daras_ai_v2.workflow_url_input import del_button, workflow_url_input
    from recipes.BulkRunner import list_view_editor
    from recipes.Functions import FunctionsPage

    def render_inputs(list_key: str, del_key: str, d: dict):
        col1, col2 = gui.columns([3, 9], responsive=True)
        with col1:
            col1.node.props["className"] += " pt-1"
            d["trigger"] = enum_selector(
                enum_cls=FunctionTrigger,
                use_selectbox=True,
                key=list_key + ":trigger",
                value=d.get("trigger"),
            )
        with col2:
            url = d.get("url") or ""
            tool_slug = get_external_tool_slug_from_url(url)
            if tool_slug:
                with gui.div(className="d-flex align-items-center"):
                    gui.write(
                        f'<a href="{url}" target="_blank">{tool_slug}</a>',
                        unsafe_allow_html=True,
                    )
                    del_button(del_key)
            else:
                workflow_url_input(
                    page_cls=FunctionsPage,
                    key=list_key + ":url",
                    internal_state=d,
                    del_key=del_key,
                    current_user=current_user,
                    include_root=False,
                )
        col2.node.children[0].props["className"] += " col-12"

    def render_section():
        from functions.composio_tools import render_inbuilt_tools_selector

        gui.session_state.setdefault(key, [{}])
        with gui.div(className="d-flex align-items-center gap-3 mb-2"):
            gui.write("###### Functions", help=FUNCTIONS_HELP_TEXT)
            gui.session_state[f"--{key}:add"] = gui.button(
                f"{icons.add} Add", type="tertiary", className="p-1 mb-2"
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
    items = _get_called_functions_items(saved_run=saved_run, trigger=trigger)
    if not items:
        return
    for item in items:
        key = f"fn-call-details-{item['id']}"
        with gui.expander(f"🛠️ Called `{item['title']}`", key=key):
            if not gui.session_state.get(key):
                continue
            gui.html(
                f'<i class="fa-regular fa-external-link-square"></i> '
                f'<a target="_blank" href="{item["url"]}">'
                "Inspect Function Call"
                "</a>"
            )

            gui.write("**Inputs**")
            gui.json(item["inputs"])

            if item["return_value"] is not None:
                gui.write("**Return value**")
                gui.json(item["return_value"])


def render_called_functions_as_html(
    *, saved_run: SavedRun, trigger: FunctionTrigger
) -> str:
    """Return HTML for functions called for a given run and trigger using a template."""
    context_items = list(
        _get_called_functions_items(saved_run=saved_run, trigger=trigger)
    )
    if not context_items:
        return ""
    context = {"called_functions": context_items}
    template = templates.get_template("functions/called_functions.html")
    return template.render(context)


def _get_called_functions_items(
    *, saved_run: SavedRun, trigger: FunctionTrigger
) -> typing.Iterable[dict]:
    """Generate data for called functions for reuse across renderers."""
    from bots.models import Workflow

    if not is_functions_enabled():
        return

    qs = saved_run.called_functions.filter(trigger=trigger.db_value)
    for called_fn in qs:
        fn_sr = called_fn.function_run
        page_cls = Workflow(fn_sr.workflow).page_cls

        pr = fn_sr.parent_published_run()
        title = pr and pr.title or "Function"

        if fn_sr.workflow == Workflow.FUNCTIONS:
            fn_vars = fn_sr.state.get("variables", {})
            fn_vars_schema = fn_sr.state.get("variables_schema", {})
            inputs = {
                key: value
                for key, value in fn_vars.items()
                if fn_vars_schema.get(key, {}).get("role") != "system"
            }
        else:
            inputs = page_cls.get_example_request(fn_sr.state)[1]
        return_value = fn_sr.state.get("return_value")

        yield dict(
            id=called_fn.id,
            title=title,
            url=fn_sr.get_app_url(),
            inputs=inputs,
            return_value=return_value,
            is_running=bool(fn_sr.run_status),
        )

    if trigger == FunctionTrigger.prompt:
        yield from _get_external_tool_calls_items(saved_run)


def _get_external_tool_calls_items(saved_run: SavedRun) -> typing.Iterable[dict]:
    final_prompt = saved_run.state.get("final_prompt")
    if not final_prompt:
        return []

    external_tools = {
        tool_slug
        for fn in saved_run.state.get("functions", [])
        if (tool_slug := get_external_tool_slug_from_url(fn["url"]))
    }

    items_by_id = {}
    for entry in final_prompt:
        if entry.get("role") == "tool":
            tool_call_id = entry["tool_call_id"]
            try:
                item = items_by_id[tool_call_id]
            except KeyError:
                continue
            return_value = entry["content"]
            try:
                return_value = json.loads(return_value)
            except json.JSONDecodeError:
                pass
            item["return_value"] = return_value
            item["is_running"] = False

        for tool_call in entry.get("tool_calls", []):
            tool_call_id = tool_call["id"]
            tool_name = tool_call["function"]["name"]
            if tool_name not in external_tools:
                continue
            inputs = tool_call["function"]["arguments"]
            try:
                inputs = json.loads(inputs)
            except json.JSONDecodeError:
                pass

            items_by_id[tool_call_id] = dict(
                id=tool_call_id,
                title=tool_name,
                url="",
                inputs=inputs,
                return_value=None,
                is_running=True,
            )

    return items_by_id.values()


def get_external_tool_slug_from_url(url: str) -> str | None:
    from daras_ai_v2.fastapi_tricks import resolve_url
    from routers.root import tool_page

    match = resolve_url(url)
    if match and match.route.name == tool_page.__name__:
        tool_slug = match.matched_params["tool_slug"]
        return tool_slug

    return None
