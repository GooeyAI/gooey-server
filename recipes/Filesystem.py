from __future__ import annotations

import html
import typing

import gooey_gui as gui
from pydantic import BaseModel, Field

from bots.models import Workflow
from functions.models import CalledFunction
from daras_ai_v2 import icons
from daras_ai_v2.base import BasePage
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.field_render import field_desc, field_title
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.mirage_fs import S3_MOUNT_PATH, run_readonly_s3_command
from managed_secrets.models import ManagedSecret
from managed_secrets.widgets import edit_secret_button_with_dialog
from workspaces.models import Workspace


class FilesystemPage(BasePage):
    title = "Filesystem"
    workflow = Workflow.FILESYSTEM
    slug_versions = ["fs", "filesystem"]
    show_settings = False
    price = 1

    DEFAULT_AGENT_TOOL_NOTES = """\
Read-only virtual filesystem over a connected S3-compatible bucket, mounted at `/s3/`.

Treat this tool as a **remote file knowledge base**. Before answering questions about \
files, logs, exports, or documents in the bucket, explore and read from `/s3/` using \
bash commands. Do not guess filenames or contents — look them up first.

**When to use**
- User asks about files, folders, logs, reports, or data stored in the bucket
- You need to discover what exists (`ls`, `find`)
- You need to read or search file contents (`cat`, `head`, `grep`)
- You need counts or summaries (`wc`, pipes)

**How to explore (read-only)**
1. `ls /s3/` — see top-level folders/files
2. `find /s3/ -type f | head -50` — discover files
3. `head -n 30 "/s3/path/to/file.txt"` — preview a file
4. `grep -r "search term" /s3/` — search across the bucket
5. Quote paths that contain spaces

**Returns** `stdout`, `stderr`, and `exit_code`. Exit code 0 = success; 1 = no matches; \
2 = command/path error.

**Limits** Read-only: no `cp`, `mv`, `rm`, `mkdir`, `>`, `>>`, or `tee`. S3 connection \
settings are already configured in this saved workflow — only pass `command`.\
"""

    class RequestModel(BaseModel):
        command: str | None = Field(
            None,
            title="Command",
            description=(
                "A read-only bash command to run against the virtual mount at "
                f"`{S3_MOUNT_PATH}`. Examples: `ls {S3_MOUNT_PATH}/`, "
                f"`grep alert {S3_MOUNT_PATH}/logs/*.jsonl | wc -l`."
            ),
        )
        s3_bucket: str | None = Field(
            None,
            title="S3 Bucket",
            description="Name of the S3-compatible bucket to mount.",
        )
        s3_endpoint_url: str | None = Field(
            None,
            title="S3 Endpoint URL",
            description=(
                "Custom endpoint for S3-compatible storage (R2, MinIO, GCS interop). "
                "Leave blank for AWS S3."
            ),
        )
        s3_region: str | None = Field(
            None,
            title="S3 Region",
            description="AWS region (e.g. `us-east-1`). Optional for custom endpoints.",
        )
        s3_prefix: str | None = Field(
            None,
            title="S3 Key Prefix",
            description="Optional key prefix within the bucket (e.g. `logs/2026/`).",
        )
        secrets: list[str] | None = Field(
            None,
            title="Secrets",
            description=(
                "Managed secrets for S3 credentials. Include secrets named "
                "`AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`.\n\n"
                "Manage your secrets in the [account keys](/account/api-keys/) section."
            ),
        )

    class ResponseModel(BaseModel):
        stdout: str | None = Field(
            None,
            title="Stdout",
            description="Standard output from the command.",
        )
        stderr: str | None = Field(
            None,
            title="Stderr",
            description="Standard error from the command.",
        )
        exit_code: int | None = Field(
            None,
            title="Exit code",
            description="Process exit code (0 = success).",
        )

    def run_v2(
        self,
        request: FilesystemPage.RequestModel,
        response: FilesystemPage.ResponseModel,
    ) -> typing.Iterator[str | None]:
        if not request.command:
            raise UserError("Please provide a bash command.")
        if not request.s3_bucket:
            raise UserError("Please provide an S3 bucket name.")

        if request.secrets:
            yield "Decrypting secrets..."
            env = dict(map_parallel(self._load_secret, request.secrets))
        else:
            env = {}

        access_key_id = env.get("AWS_ACCESS_KEY_ID")
        secret_access_key = env.get("AWS_SECRET_ACCESS_KEY")
        if not access_key_id or not secret_access_key:
            raise UserError(
                "Secrets must include managed secrets named `AWS_ACCESS_KEY_ID` and "
                "`AWS_SECRET_ACCESS_KEY`. Add them in your "
                "[account keys](/account/api-keys/) section and select them below."
            )

        yield "Running command..."

        result = run_readonly_s3_command(
            command=request.command,
            bucket=request.s3_bucket,
            endpoint_url=request.s3_endpoint_url,
            region=request.s3_region,
            prefix=request.s3_prefix,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
        )
        response.stdout = result.stdout
        response.stderr = result.stderr
        response.exit_code = result.exit_code

    def get_price_roundoff(self, state: dict) -> float:
        if CalledFunction.objects.filter(function_run=self.current_sr).exists():
            return 0
        return super().get_price_roundoff(state)

    def additional_notes(self):
        return "\nFilesystem runs are free when called from an Agent or another workflow."

    def _get_default_pr_notes(self) -> str:
        return self.DEFAULT_AGENT_TOOL_NOTES

    @classmethod
    def get_tool_call_schema(cls, state: dict) -> dict[str, typing.Any]:
        return {
            "command": {
                "type": "string",
                "description": (
                    "Read-only bash command to query the remote file knowledge base at "
                    f"`{S3_MOUNT_PATH}`. Explore before answering — do not invent paths.\n\n"
                    "Discover: `ls /s3/`, `find /s3/ -type f | head -50`\n"
                    "Read: `cat /s3/path/file.txt`, `head -n 20 \"/s3/path/with spaces/file.txt\"`\n"
                    "Search: `grep -r \"pattern\" /s3/`, `grep -i error /s3/logs/app.log`\n"
                    "Summarize: `grep alert /s3/logs/*.jsonl | wc -l`\n\n"
                    "Read-only. No cp, rm, mkdir, >, >>. Returns stdout/stderr."
                ),
            },
        }

    def _load_secret(self, name: str) -> tuple[str, str]:
        try:
            secret = ManagedSecret.objects.get(
                workspace=self.current_workspace, name=name
            )
        except ManagedSecret.DoesNotExist:
            raise UserError(
                f"Secret `{name}` not found. Please go to your "
                f"[account keys](/account/api-keys/) section and provide this value."
            )
        secret.load_value()
        return secret.name, secret.value

    def render_form_v2(self):
        gui.text_area(
            "##### " + field_title(self.RequestModel, "command"),
            key="command",
            help=field_desc(self.RequestModel, "command"),
            height=120,
        )
        gui.text_input(
            "##### " + field_title(self.RequestModel, "s3_bucket"),
            key="s3_bucket",
            help=field_desc(self.RequestModel, "s3_bucket"),
        )
        gui.text_input(
            field_title(self.RequestModel, "s3_endpoint_url"),
            key="s3_endpoint_url",
            help=field_desc(self.RequestModel, "s3_endpoint_url"),
        )
        gui.text_input(
            field_title(self.RequestModel, "s3_region"),
            key="s3_region",
            help=field_desc(self.RequestModel, "s3_region"),
        )
        gui.text_input(
            field_title(self.RequestModel, "s3_prefix"),
            key="s3_prefix",
            help=field_desc(self.RequestModel, "s3_prefix"),
        )
        self._render_secrets_input()

    def validate_form_v2(self):
        assert gui.session_state.get("command", "").strip(), "Please enter a command"
        assert gui.session_state.get("s3_bucket", "").strip(), "Please enter an S3 bucket"

    def render_output(self):
        exit_code = gui.session_state.get("exit_code")
        if exit_code is not None:
            gui.write(f"**Exit code:** `{exit_code}`")

        stdout = gui.session_state.get("stdout")
        if stdout and not callable(stdout):
            gui.write("**Stdout**")
            with gui.tag("pre", className="bg-light p-2 font-monospace"):
                gui.html(html.escape(str(stdout)))

        stderr = gui.session_state.get("stderr")
        if stderr and not callable(stderr):
            gui.write("**Stderr**")
            with gui.tag("pre", className="bg-danger bg-opacity-10 p-2 font-monospace"):
                gui.html(html.escape(str(stderr)))

    def render_run_preview_output(self, state: dict):
        command = state.get("command")
        if command:
            gui.write("**Command**")
            gui.write(f"```bash\n{command}\n```")

        stdout = state.get("stdout")
        if stdout and not callable(stdout):
            preview = str(stdout)
            if len(preview) > 500:
                preview = preview[:500] + "…"
            gui.write("**Stdout**")
            gui.write(f"```\n{preview}\n```")

        exit_code = state.get("exit_code")
        if exit_code is not None:
            gui.caption(f"Exit code: {exit_code}")

    @classmethod
    def preview_input(cls, state: dict) -> str | None:
        return state.get("command") or state.get("s3_bucket")

    def _render_secrets_input(self):
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
