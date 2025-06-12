import tempfile
import typing
from enum import Enum

import gooey_gui as gui
import requests
from pydantic import BaseModel, Field

from bots.models import Workflow
from bots.models.saved_run import SavedRun
from daras_ai_v2 import icons, settings
from daras_ai_v2.base import BasePage
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.exceptions import UserError, raise_for_status
from daras_ai_v2.field_render import field_desc, field_title
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.pydantic_validation import PydanticEnumMixin
from daras_ai_v2.variables_widget import variables_input
from functions.models import CalledFunction, VariableSchema
from managed_secrets.models import ManagedSecret
from managed_secrets.widgets import edit_secret_button_with_dialog
from workspaces.models import Workspace


class ConsoleLogs(BaseModel):
    level: typing.Literal["log", "error"]
    message: str


class CodeLanguages(PydanticEnumMixin, Enum):
    javascript = "🌎 JavaScript"
    python = "🐍 Python"


class FunctionsPage(BasePage):
    title = "Functions"
    workflow = Workflow.FUNCTIONS
    slug_versions = ["functions", "tools", "function", "fn", "functions"]
    show_settings = False
    price = 1

    class RequestModel(BaseModel):
        code: str | None = Field(
            None, title="Code", description="The code to be executed. "
        )
        language: CodeLanguages = Field(
            CodeLanguages.javascript,
            title="Language",
            description="The programming language to use.\n\n"
            "Your code is executed in a sandboxed environment via [Deno Deploy](https://deno.com/deploy) for JavaScript and [Modal Sandbox](https://modal.com/docs/reference/sandbox) for Python.",
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
            'Use them in your functions from nodejs standard `process.env.SECRET_NAME` or `os.environ["SECRET_NAME"]` in python\n\n'
            "Manage your secrets in the [account keys](/account/api-keys/) section.",
        )
        python_requirements: str | None = Field(
            None,
            title="🐍 `requirements.txt`",
            description="List of python packages to be installed in the sandbox.",
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
            description="Error from the code. If there are no errors, this will be null",
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
        if request.secrets:
            yield "Decrypting secrets..."
            env = dict(map_parallel(self._load_secret, request.secrets))
        else:
            env = None

        yield "Running your code..."

        variables = request.variables or {}

        match request.language:
            case CodeLanguages.python:
                execute_python(
                    code=request.code,
                    variables=variables,
                    env=env,
                    response=response,
                    python_requirements=request.python_requirements,
                )
            case CodeLanguages.javascript:
                execute_js(
                    sr=self.current_sr,
                    code=request.code,
                    variables=variables,
                    env=env,
                    response=response,
                )

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
        language = enum_selector(
            enum_cls=CodeLanguages,
            label="##### " + field_title(self.RequestModel, "language"),
            key="language",
            help=field_desc(self.RequestModel, "language"),
            use_selectbox=True,
        )
        gui.code_editor(
            label="##### " + field_title(self.RequestModel, "code"),
            key="code",
            language=language,
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

        if gui.session_state.get("language") == "python":
            gui.code_editor(
                label="##### " + field_title(self.RequestModel, "python_requirements"),
                key="python_requirements",
                style=dict(maxHeight="50vh"),
                help=field_desc(self.RequestModel, "python_requirements"),
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


def execute_python(
    code: str,
    variables: dict[str, typing.Any],
    env: dict[str, str] | None,
    response: "FunctionsPage.ResponseModel",
    python_requirements: str | None,
):
    import modal

    app = modal.App.lookup("my-app", create_if_missing=True)
    with tempfile.NamedTemporaryFile(suffix=".txt") as f:
        if python_requirements:
            f.write(python_requirements.encode())
            f.flush()
        sb = modal.Sandbox.create(
            "python",
            "-c",
            code,
            image=modal.Image.debian_slim().pip_install_from_requirements(f.name),
            secrets=[modal.Secret.from_dict(env or {})],
            app=app,
        )

    response.logs = []
    for line in sb.stdout:
        response.logs.append(ConsoleLogs(level="log", message=line))
    response.error = sb.stderr.read()


def execute_js(
    sr: SavedRun,
    code: str,
    variables: dict[str, typing.Any],
    env: dict[str, str] | None,
    response: "FunctionsPage.ResponseModel",
):
    tag = f"run_id={sr.run_id}&uid={sr.uid}"

    # this will run functions/executor.js in deno deploy
    r = requests.post(
        settings.DENO_FUNCTIONS_URL,
        headers={"Authorization": f"Basic {settings.DENO_FUNCTIONS_AUTH_TOKEN}"},
        json=dict(
            code=code,
            variables=variables,
            tag=tag,
            env=env,
        ),
    )
    raise_for_status(r)
    data = r.json()
    response.logs = data.get("logs")
    response.return_value = data.get("retval")
    response.error = data.get("error")
