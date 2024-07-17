import typing

import requests
from pydantic import BaseModel, Field

import gooey_ui as st
from bots.models import Workflow
from daras_ai_v2 import settings
from daras_ai_v2.base import BasePage
from daras_ai_v2.exceptions import raise_for_status
from daras_ai_v2.field_render import field_title_desc
from daras_ai_v2.prompt_vars import variables_input


class ConsoleLogs(BaseModel):
    level: typing.Literal["log", "error"]
    message: str


class FunctionsPage(BasePage):
    title = "Functions"
    workflow = Workflow.FUNCTIONS
    slug_versions = ["functions", "tools", "function", "fn", "functions"]

    class RequestModel(BaseModel):
        code: str = Field(
            None,
            title="Code",
            description="The JS code to be executed.",
        )
        variables: dict[str, typing.Any] = Field(
            {},
            title="Variables",
            description="Variables to be used in the code",
        )

    class ResponseModel(BaseModel):
        return_value: typing.Any = Field(
            None,
            title="Return value",
            description="Return value of the code. Can be any JSON object",
        )
        error: str = Field(
            None,
            title="Error",
            description="JS Error from the code. If there are no errors, this will be null",
        )
        logs: list[ConsoleLogs] = Field(
            None,
            title="Logs",
            description="Console logs from the code execution",
        )

    def run_v2(
        self,
        request: "FunctionsPage.RequestModel",
        response: "FunctionsPage.ResponseModel",
    ) -> typing.Iterator[str | None]:
        query_params = st.get_query_params()
        run_id = query_params.get("run_id")
        uid = query_params.get("uid")
        tag = f"run_id={run_id}&uid={uid}"

        yield "Running your code..."
        # this will run functions/executor.js in deno deploy
        r = requests.post(
            settings.DENO_FUNCTIONS_URL,
            headers={"Authorization": f"Basic {settings.DENO_FUNCTIONS_AUTH_TOKEN}"},
            json=dict(code=request.code, variables=request.variables or {}, tag=tag),
        )
        raise_for_status(r)
        data = r.json()
        response.logs = data.get("logs")
        response.return_value = data.get("retval")
        response.error = data.get("error")

    def render_form_v2(self):
        st.caption("##### " + field_title_desc(self.RequestModel, "code"))
        st.code_editor(key="code", language="javascript", height=300)

    def render_variables(self):
        variables_input(template_keys=["code"], allow_add=True)

    def render_output(self):
        if error := st.session_state.get("error"):
            with st.tag("pre", className="bg-danger bg-opacity-25"):
                st.html(error)

        if return_value := st.session_state.get("return_value"):
            st.write("**Return value**")
            st.json(return_value)

        logs = st.session_state.get("logs")
        if not logs:
            return

        st.write("---")
        st.write("**Logs**")
        with st.tag(
            "pre", style=dict(maxHeight=500, overflowY="auto"), className="bg-light p-2"
        ):
            for i, log in enumerate(logs):
                if log.get("level") == "error":
                    textClass = "text-danger"
                else:
                    textClass = ""
                if i > 0:
                    borderClass = "border-top"
                else:
                    borderClass = ""
                st.html(
                    log.get("message"),
                    className=f"d-block py-1 {borderClass} {textClass}",
                )
