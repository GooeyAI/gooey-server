import json
import tempfile
import typing
from enum import Enum
from functools import partial

import gooey_gui as gui
from django.utils.text import slugify

from app_users.models import AppUser
from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.field_render import field_title_desc
from daras_ai_v2.settings import templates
from functions.models import CalledFunction, FunctionTrigger

if typing.TYPE_CHECKING:
    from bots.models import SavedRun
    from daras_ai_v2.base import BasePage


def call_recipe_functions(
    *,
    saved_run: "SavedRun",
    current_user: AppUser,
    request_model: typing.Type["BasePage.RequestModel"],
    response_model: typing.Type["BasePage.ResponseModel"],
    state: dict,
    trigger: FunctionTrigger,
) -> typing.Generator[typing.Union[str, tuple[str, "LLMTool"]], None, None]:
    from daras_ai_v2.workflow_url_input import url_to_runs

    functions = state.get("functions") or []
    functions = [fun for fun in functions if fun.get("trigger") == trigger.name]
    if not functions:
        return

    request = request_model.parse_obj(state)
    variables = state.setdefault("variables", {})
    fn_vars = dict(
        web_url=saved_run.get_app_url(),
        request=json.loads(request.json(exclude_unset=True, exclude={"variables"})),
        response={k: v for k, v in state.items() if k in response_model.__fields__},
    )

    if trigger != FunctionTrigger.prompt:
        yield f"Running {trigger.name} hooks..."

    def run(sr, pr, /, **kwargs):
        result, sr = sr.submit_api_call(
            current_user=current_user,
            parent_pr=pr,
            request_body=dict(
                variables=sr.state.get("variables", {}) | variables | fn_vars | kwargs,
            ),
            deduct_credits=False,
        )

        CalledFunction.objects.create(
            saved_run=saved_run, function_run=sr, trigger=trigger.db_value
        )

        # wait for the result if its a pre request function
        if trigger == FunctionTrigger.post:
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
                if k in request_model.__fields__ or k in response_model.__fields__:
                    state[k] = v
                else:
                    variables[k] = v
        else:
            variables["return_value"] = return_value

        return return_value

    for fun in functions:
        _, sr, pr = url_to_runs(fun.url)
        if trigger != FunctionTrigger.prompt:
            run(sr, pr)
        else:
            fn_name = slugify(pr.title).replace("-", "_")
            yield fn_name, LLMTool(
                fn=partial(run, sr, pr),
                label=pr.title,
                spec={
                    "type": "function",
                    "function": {
                        "name": fn_name,
                        "description": pr.notes,
                        "parameters": {
                            "type": "object",
                            "properties": {
                                key: {"type": get_json_type(value)}
                                for key, value in sr.state.get("variables", {}).items()
                            },
                        },
                    },
                },
            )


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

    if gui.checkbox(
        f"##### {field_title_desc(BasePage.RequestModel, key)}",
        key=f"--enable-{key}",
        value=key in gui.session_state,
    ):
        gui.session_state.setdefault(key, [{}])
        with gui.div(className="d-flex align-items-center"):
            gui.write("###### Functions")
        gui.caption(
            "Functions give your workflow the ability run Javascript code (with webcalls!) allowing it execute logic, use common JS libraries or make external API calls before or after the workflow runs. <a href='/functions-help' target='_blank'>Learn more.</a>",
            unsafe_allow_html=True,
        )
        list_view_editor(
            add_btn_label="Add Function",
            add_btn_type="tertiary",
            key=key,
            render_inputs=render_function_input,
        )
    else:
        gui.session_state.pop(key, None)


def json_to_pdf(filename: str, data: str) -> str:
    html = templates.get_template("form_output.html").render(data=json.loads(data))
    pdf_bytes = html_to_pdf(html)
    if not filename.endswith(".pdf"):
        filename += ".pdf"
    return upload_file_from_bytes(filename, pdf_bytes, "application/pdf")


def html_to_pdf(html: str) -> bytes:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html)
        with tempfile.NamedTemporaryFile(suffix=".pdf") as outfile:
            page.pdf(path=outfile.name, format="A4")
            ret = outfile.read()
        browser.close()

    return ret


class LLMTool(typing.NamedTuple):
    fn: typing.Callable
    label: str
    spec: dict


class LLMTools(LLMTool, Enum):
    json_to_pdf = LLMTool(
        fn=json_to_pdf,
        label="Save JSON as PDF",
        spec={
            "type": "function",
            "function": {
                "name": json_to_pdf.__name__,
                "description": "Save JSON data to PDF",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "A short but descriptive filename for the PDF",
                        },
                        "data": {
                            "type": "string",
                            "description": "The JSON data to write to the PDF",
                        },
                    },
                    "required": ["filename", "data"],
                },
            },
        },
    )
