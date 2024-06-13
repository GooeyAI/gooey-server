import typing

import requests
from pydantic import BaseModel, Field

import gooey_ui as st
from bots.models import Workflow
from daras_ai_v2 import settings
from daras_ai_v2.base import BasePage
from daras_ai_v2.field_render import field_title_desc


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
        yield "Running your code..."
        r = requests.post(
            settings.DENO_FUNCTIONS_URL,
            headers={"Authorization": f"Basic {settings.DENO_FUNCTIONS_AUTH_TOKEN}"},
            data=request.code,
        )
        data = r.json()
        response.logs = data.get("logs")
        if r.ok:
            response.return_value = data.get("retval")
        else:
            response.error = data.get("error")

    def render_form_v2(self):
        st.text_area(
            "##### " + field_title_desc(self.RequestModel, "code"),
            key="code",
            height=500,
        )

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
