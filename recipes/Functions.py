import typing

import gooey_gui as gui
import requests
from bots.models import Workflow
from daras_ai_v2 import icons, settings
from daras_ai_v2.base import BasePage
from daras_ai_v2.exceptions import UserError, raise_for_status
from daras_ai_v2.field_render import field_desc, field_title
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.variables_widget import variables_input
from managed_secrets.models import ManagedSecret
from managed_secrets.widgets import edit_secret_button_with_dialog
from pydantic import BaseModel, Field
from workspaces.models import Workspace

from functions.models import CalledFunction, VariableSchema


class ConsoleLogs(BaseModel):
    level: typing.Literal["log", "error"]
    message: str


class FunctionsPage(BasePage):
    title = "Functions"
    workflow = Workflow.FUNCTIONS
    slug_versions = ["functions", "tools", "function", "fn", "functions"]
    show_settings = False
    price = 1

    class RequestModel(BaseModel):
        code: str | None = Field(
            None,
            title="Code",
            description="The JS code to be executed.",
        )
        variables: dict[str, typing.Any] = Field(
            {},
            title="Variables",
            description="Variables to be used in the code",
        )
        variables_schema: dict[str, VariableSchema] = Field(
            {},
            title="⌥ Variables Schema",
            description="Schema for variables to be used in the variables input",
        )
        secrets: list[str] | None = Field(
            None,
            title="Secrets",
            description="Secrets enable workflow sharing without revealing sensitive environment variables like API keys.\n"
            "Use them in your functions from nodejs standard `process.env.SECRET_NAME`\n\n"
            "Manage your secrets in the [account keys](/account/api-keys/) section.",
        )

    class ResponseModel(BaseModel):
        return_value: typing.Any | None = Field(
            None,
            title="Return value",
            description="Return value of the code. Can be any JSON object",
        )
        error: str | None = Field(
            None,
            title="Error",
            description="JS Error from the code. If there are no errors, this will be null",
        )
        logs: list[ConsoleLogs] | None = Field(
            None,
            title="Logs",
            description="Console logs from the code execution",
        )

    def run_v2(
        self,
        request: "FunctionsPage.RequestModel",
        response: "FunctionsPage.ResponseModel",
    ) -> typing.Iterator[str | None]:
        sr = self.current_sr
        tag = f"run_id={sr.run_id}&uid={sr.uid}"

        if request.secrets:
            yield "Decrypting secrets..."
            env = dict(map_parallel(self._load_secret, request.secrets))
        else:
            env = None

        yield "Running your code..."
        # this will run functions/executor.js in deno deploy
        r = requests.post(
            settings.DENO_FUNCTIONS_URL,
            headers={"Authorization": f"Basic {settings.DENO_FUNCTIONS_AUTH_TOKEN}"},
            json=dict(
                code=request.code,
                variables=request.variables or {},
                tag=tag,
                env=env,
            ),
        )
        raise_for_status(r)
        data = r.json()
        response.logs = data.get("logs")
        response.return_value = data.get("retval")
        response.error = data.get("error")

    def _load_secret(self, name: str) -> tuple[str, str]:
        try:
            secret = ManagedSecret.objects.get(
                workspace=self.current_workspace, name=name
            )
        except ManagedSecret.DoesNotExist:
            raise UserError(
                f"Secret `{name}` not found. Please go to your [account keys](/account/api-keys/) section and provide this value."
            )
        secret.load_value()
        return secret.name, secret.value

    def render_form_v2(self):
        gui.code_editor(
            label="##### " + field_title(self.RequestModel, "code"),
            key="code",
            language="javascript",
            style=dict(maxHeight="50vh"),
        )

    def get_price_roundoff(self, state: dict) -> float:
        if CalledFunction.objects.filter(function_run=self.current_sr).exists():
            return 0
        return super().get_price_roundoff(state)

    def additional_notes(self):
        return "\nFunctions are free if called from another workflow."

    def render_variables(self):
        variables_input(
            template_keys=["code"],
            allow_add=True,
            description="Pass custom parameters to your function and access the parent workflow data. "
            "Variables will be passed down as the first argument to your anonymous JS function.",
            exclude=self.fields_to_save(),
        )

        options = set(gui.session_state.get("secrets") or [])
        with gui.div(className="d-flex align-items-center gap-3 mb-2"):
            gui.markdown(
                "###### "
                + '<i class="fa-regular fa-shield-keyhole"></i> '
                + field_title(self.RequestModel, "secrets"),
                help=field_desc(self.RequestModel, "secrets"),
                unsafe_allow_html=True,
            )
            try:
                workspace = self.current_workspace
            except Workspace.DoesNotExist:
                pass
            else:
                edit_secret_button_with_dialog(
                    workspace,
                    self.request.user,
                    trigger_label=f"{icons.add} Add",
                    trigger_type="tertiary",
                    trigger_className="p-1 mb-2",
                )
                options |= set(
                    workspace.managed_secrets.order_by("-created_at").values_list(
                        "name", flat=True
                    )
                )
        with gui.div(className="font-monospace"):
            gui.multiselect(
                label="",
                options=list(options),
                key="secrets",
                allow_none=True,
            )

    def render_output(self):
        if error := gui.session_state.get("error"):
            with gui.tag("pre", className="bg-danger bg-opacity-25"):
                gui.html(error)

        if return_value := gui.session_state.get("return_value"):
            gui.write("**Return value**")
            gui.json(return_value)

        logs = gui.session_state.get("logs")
        if not logs:
            return

        gui.write("---")
        gui.write("**Logs**")
        with gui.tag(
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
                gui.html(
                    log.get("message"),
                    className=f"d-block py-1 {borderClass} {textClass}",
                )
