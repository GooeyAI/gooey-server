import json
import typing

import gooey_gui as gui
from django.utils.text import slugify

from app_users.models import AppUser
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.field_render import field_title_desc
from functions.models import CalledFunction, FunctionTrigger

if typing.TYPE_CHECKING:
    from bots.models import SavedRun
    from daras_ai_v2.base import BasePage, JsonTypes
    from workspaces.models import Workspace


class LLMTool:
    def __init__(self, function_url: str):
        from daras_ai_v2.workflow_url_input import url_to_runs

        self.function_url = function_url

        _, fn_sr, fn_pr = url_to_runs(function_url)
        self._function_runs = (fn_sr, fn_pr)

        self.name = slugify(fn_pr.title).replace("-", "_")
        self.label = fn_pr.title

        fn_vars = fn_sr.state.get("variables", {})
        fn_vars_schema = fn_sr.state.get("variables_schema", {})
        self.spec = {
            "type": "function",
            "function": {
                "name": self.name,
                "description": fn_pr.notes,
                "parameters": {
                    "type": "object",
                    "properties": {
                        key: {
                            "type": schema.get("type", get_json_type(value)),
                            "description": schema.get("description", ""),
                        }
                        for key, value in fn_vars.items()
                        if (schema := fn_vars_schema.get(key, {}))
                        and schema.get("role") != "system"
                    },
                },
            },
        }

    def bind(
        self,
        saved_run: "SavedRun",
        workspace: "Workspace",
        current_user: AppUser,
        request_model: typing.Type["BasePage.RequestModel"],
        response_model: typing.Type["BasePage.ResponseModel"],
        state: dict,
        trigger: FunctionTrigger,
    ) -> "LLMTool":
        self.saved_run = saved_run
        self.workspace = workspace
        self.current_user = current_user
        self.request_model = request_model
        self.response_model = response_model
        self.state = state
        self.trigger = trigger
        return self

    def __call__(self, **kwargs):
        try:
            self.saved_run
        except AttributeError:
            raise RuntimeError("This LLMTool instance is not yet bound")

        fn_sr, fn_pr = self._function_runs

        state_vars = self.state.setdefault("variables", {})
        state_vars_schema = self.state.setdefault("variables_schema", {})
        system_vars, system_vars_schema = self._get_system_vars()
        fn_vars = (
            (fn_sr.state.get("variables") or {}) | state_vars | system_vars | kwargs
        )
        fn_vars_schema = (
            (fn_sr.state.get("variables_schema") or {})
            | state_vars_schema
            | system_vars_schema
        )
        result, fn_sr = fn_sr.submit_api_call(
            workspace=self.workspace,
            current_user=self.current_user,
            parent_pr=fn_pr,
            request_body=dict(variables=fn_vars, variables_schema=fn_vars_schema),
            deduct_credits=False,
        )

        CalledFunction.objects.create(
            saved_run=self.saved_run, function_run=fn_sr, trigger=self.trigger.db_value
        )

        # wait for the result if its a pre request function
        if self.trigger == FunctionTrigger.post:
            return
        fn_sr.wait_for_celery_result(result)
        # if failed, raise error
        if fn_sr.error_msg:
            raise RuntimeError(fn_sr.error_msg)

        # save the output from the function
        return_value = fn_sr.state.get("return_value")
        if return_value is not None:
            if isinstance(return_value, dict):
                for k, v in return_value.items():
                    if (
                        k in self.request_model.__fields__
                        or k in self.response_model.__fields__
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
        request = self.request_model.parse_obj(self.state)
        system_vars = dict(
            web_url=self.saved_run.get_app_url(),
            request=json.loads(request.json(exclude_unset=True, exclude={"variables"})),
            response={
                k: v
                for k, v in self.state.items()
                if k in self.response_model.__fields__
            },
        )
        system_vars_schema = {var: {"role": "system"} for var in system_vars}

        return system_vars, system_vars_schema


def call_recipe_functions(
    *,
    saved_run: "SavedRun",
    workspace: "Workspace",
    current_user: AppUser,
    request_model: typing.Type["BasePage.RequestModel"],
    response_model: typing.Type["BasePage.ResponseModel"],
    state: dict,
    trigger: FunctionTrigger,
) -> typing.Iterable[str]:
    yield f"Running {trigger.name} hooks..."
    for tool in get_tools_from_state(state, trigger):
        tool.bind(
            saved_run=saved_run,
            workspace=workspace,
            current_user=current_user,
            request_model=request_model,
            response_model=response_model,
            state=state,
            trigger=trigger,
        )
        tool()


def get_tools_from_state(
    state: dict, trigger: FunctionTrigger
) -> typing.Iterable[LLMTool]:

    functions = state.get("functions")
    if not functions:
        return
    for function in functions:
        if function.get("trigger") != trigger.name:
            continue
        yield LLMTool(function.get("url"))


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
    from recipes.BulkRunner import list_view_editor
    from daras_ai_v2.base import BasePage

    def render_function_input(list_key: str, del_key: str, d: dict):
        from daras_ai_v2.workflow_url_input import workflow_url_input
        from recipes.Functions import FunctionsPage

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
            workflow_url_input(
                page_cls=FunctionsPage,
                key=list_key + ":url",
                internal_state=d,
                del_key=del_key,
                current_user=current_user,
                include_root=False,
            )
        col2.node.children[0].props["className"] += " col-12"

    if gui.switch(
        f"##### {field_title_desc(BasePage.RequestModel, key)}",
        key=f"--enable-{key}",
        value=key in gui.session_state,
        className="mb-2",
    ):
        with gui.div(className="ps-1"):
            gui.session_state.setdefault(key, [{}])
            with gui.div(className="d-flex align-items-center"):
                gui.write(
                    "###### Functions",
                    help="Functions give your workflow the ability run Javascript code (with webcalls!) allowing it execute logic, use common JS libraries or make external API calls before or after the workflow runs.\n"
                    "<a href='/functions-help' target='_blank'>Learn more.</a>",
                )
            list_view_editor(
                add_btn_label="Add Function",
                add_btn_type="tertiary",
                key=key,
                render_inputs=render_function_input,
            )
    else:
        gui.session_state.pop(key, None)


def render_called_functions(*, saved_run: "SavedRun", trigger: FunctionTrigger):
    from recipes.Functions import FunctionsPage
    from daras_ai_v2.breadcrumbs import get_title_breadcrumbs

    if not is_functions_enabled():
        return
    qs = saved_run.called_functions.filter(trigger=trigger.db_value)
    if not qs.exists():
        return
    for called_fn in qs:
        fn_sr = called_fn.function_run
        tb = get_title_breadcrumbs(
            FunctionsPage,
            fn_sr,
            fn_sr.parent_published_run(),
        )
        title = (tb.published_title and tb.published_title.title) or tb.h1_title
        key = f"fn-call-details-{called_fn.id}"
        with gui.expander(f"🧩 Called `{title}`", key=key):
            if not gui.session_state.get(key):
                continue
            gui.html(
                f'<i class="fa-regular fa-external-link-square"></i> <a target="_blank" href="{fn_sr.get_app_url()}">'
                "Inspect Function Call"
                "</a>"
            )

            fn_vars = fn_sr.state.get("variables", {})
            fn_vars_schema = fn_sr.state.get("variables_schema", {})
            inputs = {
                key: value
                for key, value in fn_vars.items()
                if fn_vars_schema.get(key, {}).get("role") != "system"
            }
            gui.write("**Inputs**")
            gui.json(inputs)

            return_value = fn_sr.state.get("return_value")
            if return_value is not None:
                gui.write("**Return value**")
                gui.json(return_value)
