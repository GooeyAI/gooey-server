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
    from daras_ai_v2.base import BasePage
    from workspaces.models import Workspace


class LLMTool:
    def __init__(self, function_url: str):
        from daras_ai_v2.workflow_url_input import url_to_runs

        self.function_url = function_url

        _, sr, pr = url_to_runs(function_url)
        self._function_runs = (sr, pr)

        self.name = slugify(pr.title).replace("-", "_")
        self.label = pr.title

        self.spec = {
            "type": "function",
            "function": {
                "name": self.name,
                "description": pr.notes,
                "parameters": {
                    "type": "object",
                    "properties": {
                        key: {"type": get_json_type(value)}
                        for key, value in sr.state.get("variables", {}).items()
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

        request = self.request_model.parse_obj(self.state)
        variables = self.state.setdefault("variables", {})
        fn_vars = dict(
            web_url=self.saved_run.get_app_url(),
            request=json.loads(request.json(exclude_unset=True, exclude={"variables"})),
            response={
                k: v
                for k, v in self.state.items()
                if k in self.response_model.__fields__
            },
        )

        sr, pr = self._function_runs
        result, sr = sr.submit_api_call(
            workspace=self.workspace,
            current_user=self.current_user,
            parent_pr=pr,
            request_body=dict(
                variables=sr.state.get("variables", {}) | variables | fn_vars | kwargs,
            ),
            deduct_credits=False,
        )

        CalledFunction.objects.create(
            saved_run=self.saved_run, function_run=sr, trigger=self.trigger.db_value
        )

        # wait for the result if its a pre request function
        if self.trigger == FunctionTrigger.post:
            return
        sr.wait_for_celery_result(result)
        # if failed, raise error
        if sr.error_msg:
            raise RuntimeError(sr.error_msg)

        # save the output from the function
        return_value = sr.state.get("return_value")
        if return_value is None:
            return
        if isinstance(return_value, dict):
            for k, v in return_value.items():
                if (
                    k in self.request_model.__fields__
                    or k in self.response_model.__fields__
                ):
                    self.state[k] = v
                else:
                    variables[k] = v
        else:
            variables["return_value"] = return_value

        return return_value


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


def get_json_type(val) -> str:
    match val:
        case list() | tuple() | set():
            return "array"
        case str():
            return "string"
        case int() | float() | complex():
            return "number"
        case bool():
            return "boolean"
        case _:
            return "object"


def render_called_functions(*, saved_run: "SavedRun", trigger: FunctionTrigger):
    from recipes.Functions import FunctionsPage
    from daras_ai_v2.breadcrumbs import get_title_breadcrumbs

    if not is_functions_enabled():
        return
    qs = saved_run.called_functions.filter(trigger=trigger.db_value)
    if not qs.exists():
        return
    for called_fn in qs:
        tb = get_title_breadcrumbs(
            FunctionsPage,
            called_fn.function_run,
            called_fn.function_run.parent_published_run(),
        )
        title = (tb.published_title and tb.published_title.title) or tb.h1_title
        key = f"fn-call-details-{called_fn.id}"
        with gui.expander(f"🧩 Called `{title}`", key=key):
            if not gui.session_state.get(key):
                continue
            gui.html(
                f'<i class="fa-regular fa-external-link-square"></i> <a target="_blank" href="{called_fn.function_run.get_app_url()}">'
                "Inspect Function Call"
                "</a>"
            )
            return_value = called_fn.function_run.state.get("return_value")
            if return_value is not None:
                gui.json(return_value, expanded=True)


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
