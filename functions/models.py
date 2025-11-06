from __future__ import annotations

import typing

import gooey_gui as gui
from django.db import models
from pydantic import BaseModel, Field
from typing_extensions import NotRequired, TypedDict

from daras_ai_v2 import icons
from daras_ai_v2.custom_enum import GooeyEnum
from daras_ai_v2.pydantic_validation import HttpUrlStr

if typing.TYPE_CHECKING:
    from app_users.models import AppUser
    from bots.models import PublishedRun
    from workspaces.models import Workspace


class _TriggerData(typing.NamedTuple):
    label: str
    db_value: int


class ScopeParts(GooeyEnum):
    workspace = "workspaces"
    member = "members"
    saved_workflow = "saved"
    platform_user = "users"
    deployment = "deployments"
    conversation = "conversations"


class FunctionScope(typing.NamedTuple):
    icon: str
    label: str
    parts: tuple[ScopeParts] = []


class FunctionScopes(FunctionScope, GooeyEnum):
    workspace = FunctionScope(
        icon=icons.company,
        label="Workspace Members",
        parts=(ScopeParts.workspace,),
    )

    workspace_member = FunctionScope(
        icon=icons.profile,
        label="My Runs & Deployments",
        parts=(ScopeParts.workspace, ScopeParts.member),
    )

    deployment_user = FunctionScope(
        icon=f'<img align="left" width="24" height="24" src="{icons.integrations_img}">',
        label="&nbsp; User of any Deployment",
        parts=(ScopeParts.workspace, ScopeParts.deployment, ScopeParts.platform_user),
    )

    saved_workflow = FunctionScope(
        icon=icons.save,
        label="Saved Workflow",
        parts=(ScopeParts.workspace, ScopeParts.saved_workflow),
    )
    saved_workflow_user = FunctionScope(
        icon='<i class="fa-regular fa-user-message"></i>',
        label="User of Saved Workflow",
        parts=(
            ScopeParts.workspace,
            ScopeParts.saved_workflow,
            ScopeParts.platform_user,
        ),
    )

    conversation = FunctionScope(
        icon='<i class="fa-regular fa-message"></i>',
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
                    label = f'<img align="left" src="{photo}" style="width: 24px; height: 24px; border-radius: 50%; object-fit: cover;"> &nbsp; {label}'
                return label

            case cls.deployment_user if workspace:
                icon = (
                    '<div style="position: relative; display: inline-block; margin-left: -4px; margin-right: 10px;">'
                    f"{scope.icon}"
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
                icon = f'<img align="left" src="{photo_url}" style="width: 24px; height: 24px; border-radius: 50%; object-fit: cover;">'

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
        user: AppUser,
        published_run: PublishedRun,
    ) -> str:
        if scope:
            scope_parts = set(scope.parts)
        else:
            scope_parts = {ScopeParts.workspace}

        parts = []
        if ScopeParts.workspace in scope_parts:
            parts += [ScopeParts.workspace.value, workspace.id]
        if ScopeParts.member in scope_parts:
            parts += [ScopeParts.member.value, user.id]
        if ScopeParts.saved_workflow in scope_parts:
            parts += [ScopeParts.saved_workflow.value, published_run.published_run_id]
        variables = gui.session_state.get("variables", {})
        if ScopeParts.deployment in scope_parts:
            parts += [ScopeParts.deployment.value, variables.get("integration_id")]
        if ScopeParts.platform_user in scope_parts:
            platform_user_id = (
                variables.get("slack_user_id")
                or variables.get("web_user_id")
                or variables.get("user_wa_phone_number")
                or variables.get("user_twilio_phone_number")
            )
            parts += [ScopeParts.platform_user.value, platform_user_id]
        if ScopeParts.conversation in scope_parts:
            parts += [ScopeParts.conversation.value, variables.get("conversation_id")]

        return "/".join(str(part) for part in parts if part)


class FunctionTrigger(_TriggerData, GooeyEnum):
    prompt = _TriggerData(label="✨ Prompt", db_value=3)
    pre = _TriggerData(label="⏪ Before", db_value=1)
    post = _TriggerData(label="⏩ After", db_value=2)


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
    role: NotRequired[typing.Literal["user", "system"]]
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

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.saved_run} -> {self.function_run} ({self.trigger})"
