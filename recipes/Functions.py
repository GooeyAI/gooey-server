import html
import json
import os
import tempfile
import typing
from enum import Enum

from furl import furl
import gooey_gui as gui
import requests
from pydantic import BaseModel, Field

from bots.models import Workflow
from bots.models.saved_run import SavedRun
from celeryapp.tasks import update_gcs_content_types
from daras_ai_v2 import gcs_v2, icons, settings
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
        gpu: (
            typing.Literal[
                "T4",
                "L4",
                "A10G",
                "A100-40GB",
                "A100-80GB",
                "L40S",
                "H100",
                "H200",
                "B200",
            ]
            | None
        ) = Field(
            None,
            title="GPU",
            description="GPU to be used for the code execution. Only available for Python.",
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
                    workspace_id=self.current_workspace.id,
                    code=request.code,
                    variables=variables,
                    env=env,
                    response=response,
                    python_requirements=request.python_requirements,
                    gpu=request.gpu,
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

    def get_price_roundoff(self, state: dict) -> float:
        if CalledFunction.objects.filter(function_run=self.current_sr).exists():
            return 0
        return super().get_price_roundoff(state)

    def additional_notes(self):
        return "\nFunctions are free if called from another workflow."

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
                gui.html(html.escape(error))

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
                    html.escape(log.get("message")),
                    className=f"d-block py-1 {borderClass} {textClass}",
                )


def execute_python(
    *,
    workspace_id: str,
    code: str,
    variables: dict[str, typing.Any],
    env: dict[str, str] | None,
    response: "FunctionsPage.ResponseModel",
    python_requirements: str | None,
    gpu: str | None,
    output_limit: int = 256_000,
):
    import modal

    executor_code = (settings.BASE_DIR / "functions/executor.py").read_text()
    code += "\n\n" + executor_code

    app = modal.App.lookup("gooey-functions", create_if_missing=True)
    with (
        tempfile.NamedTemporaryFile(suffix=".txt") as f,
        modal.Volume.ephemeral() as vol,
    ):
        if python_requirements:
            f.write(python_requirements.encode())
            f.flush()
        bucket_path = f"workspaces/{workspace_id}/functions/"
        prefix_url = os.path.join(gcs_v2.GCS_BUCKET_URL, bucket_path)
        sb = modal.Sandbox.create(
            "python",
            "-c",
            code,
            json.dumps(variables),
            prefix_url,
            app=app,
            image=modal.Image.debian_slim().pip_install_from_requirements(f.name),
            secrets=[modal.Secret.from_dict(env or {})],
            workdir="/workspace",
            volumes={
                "/output": vol,
                "/workspace": modal.CloudBucketMount(
                    bucket_endpoint_url=gcs_v2.GCS_BASE_URL,
                    bucket_name=gcs_v2.GCS_BUCKET_NAME,
                    key_prefix=bucket_path,
                    secret=modal.Secret.from_name("gooey-gcs-writer"),
                ),
            },
            gpu=gpu,
            timeout=30 * 60,  # 30 minutes
        )

    response.logs = []
    total = 0
    for line in sb.stdout:
        total += len(line)
        if total > output_limit:  # limit to 256KB
            response.logs.append(
                ConsoleLogs(level="error", message="Output too large, truncated.")
            )
            break
        response.logs.append(ConsoleLogs(level="log", message=line))
    response.error = sb.stderr.read()[:output_limit]

    sb.wait()

    try:
        ret_bytes = b"".join(vol.read_file("return_value.json"))
        if len(ret_bytes) > output_limit:  # limit to 256KB
            raise ValueError("Return value is too large, must be less than 256KB.")
        response.return_value = json.loads(ret_bytes.decode())
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    sb.terminate()

    update_gcs_content_types.delay(
        extract_gcs_urls(response.return_value, prefix_url, {})
    )


def extract_gcs_urls(
    obj: typing.Any, prefix_url: str, ret: dict[str, str], mime_type: str | None = None
) -> dict[str, str]:
    import mimetypes

    match obj:
        case dict():
            mime_type = obj.get("mime_type")
            for val in obj.values():
                extract_gcs_urls(val, prefix_url, ret, mime_type)
        case list():
            for val in obj:
                extract_gcs_urls(val, prefix_url, ret, mime_type)
        case str() if obj.startswith(prefix_url):
            mime_type = mime_type or mimetypes.guess_type(furl(obj).pathstr)[0]
            if mime_type:
                ret[obj] = mime_type
    return ret


def execute_js(
    *,
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
