from __future__ import annotations

import typing

from django.db import models
from pydantic import BaseModel, Field
from typing_extensions import NotRequired, TypedDict

from daras_ai_v2 import icons
from daras_ai_v2.custom_enum import GooeyEnum
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.pydantic_validation import HttpUrlStr

if typing.TYPE_CHECKING:
    from app_users.models import AppUser
    from bots.models import PublishedRun, SavedRun
    from workspaces.models import Workspace
    from memory.models import MemoryEntry


class _TriggerData(typing.NamedTuple):
    label: str
    db_value: int


class ScopePart(typing.NamedTuple):
    value: str
    label: str
    icon: str


class ScopeParts(ScopePart, GooeyEnum):
    workspace = ScopePart(
        value="workspaces",
        label="Workspace",
        icon=icons.company,
    )
    member = ScopePart(
        value="members",
        label="Member",
        icon=icons.profile,
    )
    saved_workflow = ScopePart(
        value="saved",
        label="Saved Workflow",
        icon=icons.save,
    )
    platform_user = ScopePart(
        value="users",
        label="Platform User",
        icon=icons.platform_user,
    )
    deployment = ScopePart(
        value="deployments",
        label="Deployment",
        icon=icons.deployment,
    )
    conversation = ScopePart(
        value="conversations",
        label="Conversation",
        icon=icons.conversation,
    )

    def get_user_id_fmt(
        self,
        *,
        workspace: Workspace,
        user: AppUser | None,
        published_run: PublishedRun | None,
        variables: dict,
    ) -> str:
        value = None
        match self:
            case ScopeParts.workspace:
                value = workspace.id
            case ScopeParts.member:
                if user is None:
                    raise UserError("Missing user for member scope.")
                value = user.id
            case ScopeParts.saved_workflow:
                if published_run is None:
                    raise UserError("Missing published run for saved workflow scope.")
                value = published_run.published_run_id
            case ScopeParts.platform_user:
                value = _resolve_platform_user(variables)
            case ScopeParts.deployment:
                value = variables.get("integration_id")
            case ScopeParts.conversation:
                value = variables.get("conversation_id")
        if value:
            return f"{self.value}/{value}"
        else:
            return str(self.value)


class FunctionScope(typing.NamedTuple):
    db_value: int
    icon: str
    label: str
    parts: typing.Sequence[ScopeParts] = ()


class FunctionScopes(FunctionScope, GooeyEnum):
    workspace = FunctionScope(
        db_value=1,
        icon=ScopeParts.workspace.icon,
        label="Workspace Members",
        parts=(ScopeParts.workspace,),
    )

    workspace_member = FunctionScope(
        db_value=2,
        icon=ScopeParts.member.icon,
        label="My Runs & Deployments",
        parts=(ScopeParts.workspace, ScopeParts.member),
    )

    deployment_user = FunctionScope(
        db_value=3,
        icon=ScopeParts.deployment.icon,
        label="User of any Deployment",
        parts=(ScopeParts.workspace, ScopeParts.deployment, ScopeParts.platform_user),
    )

    saved_workflow = FunctionScope(
        db_value=4,
        icon=ScopeParts.saved_workflow.icon,
        label="Saved Workflow",
        parts=(ScopeParts.workspace, ScopeParts.saved_workflow),
    )
    saved_workflow_user = FunctionScope(
        db_value=5,
        icon=ScopeParts.platform_user.icon,
        label="User of Saved Workflow",
        parts=(
            ScopeParts.workspace,
            ScopeParts.saved_workflow,
            ScopeParts.platform_user,
        ),
    )

    conversation = FunctionScope(
        db_value=6,
        icon=ScopeParts.conversation.icon,
        label="Chat Conversation",
        parts=(
            ScopeParts.workspace,
            ScopeParts.deployment,
            ScopeParts.platform_user,
            ScopeParts.conversation,
        ),
    )

    @classmethod
    def format_label(
        cls,
        name: str | None,
        workspace: Workspace | None,
        user: AppUser | None,
        published_run: PublishedRun | None,
    ) -> str:
        scope = cls.get(name)
        if not scope:
            return "Select Scope"
        match scope:
            case cls.workspace if workspace and not workspace.is_personal:
                return f"{workspace.display_html()} Members"

            case cls.workspace_member if user:
                label = f"Only I ({user.full_name()})"
                photo = user.get_photo()
                if photo:
                    label = f'<img src="{photo}" style="width: 24px; height: 24px; border-radius: 50%; object-fit: cover;"> &nbsp; {label}'
                return label

            case cls.deployment_user if workspace:
                icon = (
                    '<div style="position: relative; display: inline-block; margin-left: -4px; margin-right: 10px;">'
                    f'<img width="24" height="24" src="{icons.integrations_img}">'
                    '<span class="fa-stack" style="position: absolute; bottom: -12px; left: 8px;">'
                    '<i class="fa-solid fa-circle fa-xl" style="color: rgba(200, 200, 200, 0.6);"></i>'
                    '<i class="fa-solid fa-user-message fa-xs fa-stack-1x" color="darkslategrey"></i>'
                    "</span>"
                    "</div>"
                )
                if workspace.is_personal:
                    return f"{icon} User of any Deployment by Me ({workspace.display_name()})"
                else:
                    return (
                        f"{icon} User of any Deployment on {workspace.display_name()}"
                    )

            case cls.saved_workflow | cls.saved_workflow_user if published_run:
                from recipes.VideoBots import VideoBotsPage

                if published_run.photo_url:
                    photo_url = published_run.photo_url
                else:
                    photo_url = VideoBotsPage.get_root_pr().photo_url
                icon = f'<img src="{photo_url}" style="width: 24px; height: 24px; border-radius: 50%; object-fit: cover;">'

                if scope == cls.saved_workflow_user:
                    icon = (
                        '<div style="position: relative; display: inline-block; margin-left: -4px; margin-right: 10px;">'
                        f"{icon}"
                        '<span class="fa-stack" style="position: absolute; bottom: -12px; left: 8px;">'
                        '<i class="fa-solid fa-circle fa-xl" style="color: rgba(200, 200, 200, 0.6);"></i>'
                        '<i class="fa-solid fa-user-message fa-xs fa-stack-1x" color="darkslategrey"></i>'
                        "</span>"
                        "</div>"
                    )
                    return f"{icon} User of {published_run.title}"
                else:
                    return f"{icon} &nbsp; {published_run.title}"

            case _:
                return f"{scope.icon} {scope.label}"

    @classmethod
    def get_user_id_for_scope(
        cls,
        scope: FunctionScopes | None,
        workspace: Workspace,
        user: AppUser | None = None,
        published_run: PublishedRun | None = None,
        variables: dict | None = None,
    ) -> str:
        if scope is None:
            scope = cls.workspace
        return "/".join(
            part.get_user_id_fmt(
                workspace=workspace,
                user=user,
                published_run=published_run,
                variables=variables or {},
            )
            for part in scope.parts
        )

    def build_memory_entry(
        self,
        *,
        saved_run: SavedRun,
        workspace: Workspace,
        user: AppUser | None,
        published_run: PublishedRun | None,
        variables: dict | None = None,
    ) -> MemoryEntry:
        from memory.models import MemoryEntry

        variables = variables or {}

        return MemoryEntry(
            user_id=self.get_user_id_for_scope(
                scope=self,
                workspace=workspace,
                user=user,
                published_run=published_run,
                variables=variables,
            ),
            saved_run=saved_run,
            scope=self.db_value,
            workspace=workspace,
            member=user,
            saved_workflow=published_run,
            platform_user=_resolve_platform_user(variables) or "",
            deployment_id=_decode_api_hashid(variables.get("integration_id")),
            conversation_id=_decode_api_hashid(variables.get("conversation_id")),
        )


def _resolve_platform_user(variables: dict) -> str | None:
    return (
        variables.get("slack_user_id")
        or variables.get("web_user_id")
        or variables.get("user_wa_phone_number")
        or variables.get("user_twilio_phone_number")
    )


def _decode_api_hashid(value: str | None) -> int | None:
    if not value:
        return None
    # Imported lazily: routers.bots_api imports the models layer, so a top-level
    # import here would create a circular import.
    from routers.bots_api import api_hashids

    decoded = api_hashids.decode(value)
    if not decoded:
        return None
    return decoded[0]


class FunctionTrigger(_TriggerData, GooeyEnum):
    prompt = _TriggerData(label=f"{icons.llm_tool} LLM Tool", db_value=3)
    pre = _TriggerData(label=f"{icons.before} Before", db_value=1)
    post = _TriggerData(label=f"{icons.after} After", db_value=2)
    parallel = _TriggerData(label=f"{icons.parallel} Parallel", db_value=4)


class RecipeFunction(BaseModel):
    url: HttpUrlStr = Field(
        title="URL",
        description="The URL of the [function](https://gooey.ai/functions) to call.",
    )
    trigger: FunctionTrigger.api_choices = Field(
        title="Trigger",
        description="When to run this function. `pre` runs before the recipe, `post` runs after the recipe.",
    )
    logo: str | None = Field(
        None,
        title="Logo",
        description="The logo of the function.",
    )
    label: str | None = Field(
        None,
        title="Label",
        description="The label of the function.",
    )
    scope: str | None = Field(
        None,
        title="Scope",
        description="The scope of the function.",
    )


JsonTypes = typing.Literal["string", "number", "boolean", "array", "object"]


class VariableSchema(TypedDict):
    type: NotRequired[JsonTypes]
    role: NotRequired[typing.Literal["user", "system", "prompt"]]
    description: NotRequired[str]


class CalledFunctionResponse(BaseModel):
    url: str
    trigger: FunctionTrigger.api_choices
    return_value: typing.Any

    @classmethod
    def from_db(cls, called_fn: "CalledFunction") -> "CalledFunctionResponse":
        return cls(
            url=called_fn.function_run.get_app_url(),
            trigger=FunctionTrigger.from_db(called_fn.trigger).name,
            return_value=called_fn.function_run.state.get("return_value"),
        )


class CalledFunction(models.Model):
    saved_run = models.ForeignKey(
        "bots.SavedRun",
        on_delete=models.CASCADE,
        related_name="called_functions",
    )
    function_run = models.ForeignKey(
        "bots.SavedRun",
        on_delete=models.CASCADE,
        related_name="called_by_runs",
    )
    trigger = models.IntegerField(
        choices=FunctionTrigger.db_choices(),
    )
    tool_name = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.saved_run} -> {self.function_run} ({self.trigger})"
