import json
import tempfile
import typing
from enum import Enum

from pydantic import BaseModel

import gooey_ui as st
from app_users.models import AppUser
from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.field_render import field_title_desc
from daras_ai_v2.settings import templates
from functions.models import CalledFunction, FunctionTrigger

if typing.TYPE_CHECKING:
    from bots.models import SavedRun


def call_recipe_functions(
    *,
    saved_run: "SavedRun",
    current_user: AppUser,
    request_model: typing.Type[BaseModel],
    response_model: typing.Type[BaseModel],
    state: dict,
    trigger: FunctionTrigger,
):
    from daras_ai_v2.workflow_url_input import url_to_runs
    from gooeysite.bg_db_conn import get_celery_result_db_safe

    request = request_model.parse_obj(state)

    functions = getattr(request, "functions", None) or []
    functions = [fun for fun in functions if fun.trigger == trigger.name]
    if not functions:
        return
    variables = state.setdefault("variables", {})
    fn_vars = dict(
        web_url=saved_run.get_app_url(),
        request=json.loads(request.json(exclude_unset=True, exclude={"variables"})),
        response={k: v for k, v in state.items() if k in response_model.__fields__},
    )

    yield f"Running {trigger.name} hooks..."

    for fun in functions:
        # run the function
        page_cls, sr, pr = url_to_runs(fun.url)
        result, sr = sr.submit_api_call(
            current_user=current_user,
            parent_pr=pr,
            request_body=dict(
                variables=sr.state.get("variables", {}) | variables | fn_vars,
            ),
        )

        CalledFunction.objects.create(
            saved_run=saved_run, function_run=sr, trigger=trigger.db_value
        )

        # wait for the result if its a pre request function
        if trigger == FunctionTrigger.post:
            continue
        get_celery_result_db_safe(result)
        sr.refresh_from_db()
        # if failed, raise error
        if sr.error_msg:
            raise RuntimeError(sr.error_msg)

        # save the output from the function
        return_value = sr.state.get("return_value")
        if return_value is None:
            continue
        if isinstance(return_value, dict):
            for k, v in return_value.items():
                if k in request_model.__fields__ or k in response_model.__fields__:
                    state[k] = v
                else:
                    variables[k] = v
        else:
            variables["return_value"] = return_value


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
        st.write(f"###### 🧩 Called [{title}]({called_fn.function_run.get_app_url()})")
        return_value = called_fn.function_run.state.get("return_value")
        if return_value is not None:
            st.json(return_value)
            st.newline()


def is_functions_enabled(key="functions") -> bool:
    return bool(st.session_state.get(f"--enable-{key}"))


def functions_input(current_user: AppUser, key="functions"):
    from recipes.BulkRunner import list_view_editor
    from daras_ai_v2.base import BasePage

    def render_function_input(list_key: str, del_key: str, d: dict):
        from daras_ai_v2.workflow_url_input import workflow_url_input
        from recipes.Functions import FunctionsPage

        col1, col2 = st.columns([2, 10], responsive=False)
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
            )

    if st.checkbox(
        f"##### {field_title_desc(BasePage.RequestModel, key)}",
        key=f"--enable-{key}",
        value=key in st.session_state,
    ):
        st.session_state.setdefault(key, [{}])
        list_view_editor(
            add_btn_label="➕ Add Function",
            key=key,
            render_inputs=render_function_input,
        )
        st.write("---")
    else:
        st.session_state.pop(key, None)


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


class LLMTools(Enum):
    json_to_pdf = (
        json_to_pdf,
        "Save JSON as PDF",
        {
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
    # send_reply_buttons = (print, "Send back reply buttons to the user.", {})

    def __new__(cls, fn: typing.Callable, label: str, spec: dict):
        obj = object.__new__(cls)
        obj._value_ = fn.__name__
        obj.fn = fn
        obj.label = label
        obj.spec = spec
        return obj

    # def __init__(self, *args, **kwargs):
    #     self._value_ = self.name
