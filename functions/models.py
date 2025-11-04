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
    label: str
    parts: tuple[ScopeParts] = []


class FunctionScopes(FunctionScope, GooeyEnum):
    workspace_member = FunctionScope(
        label=f"{icons.profile} My Runs & Deployments",
        parts=(ScopeParts.workspace, ScopeParts.member),
    )

    saved_workflow = FunctionScope(
        label=f"{icons.save} Saved Workflow",
        parts=(ScopeParts.workspace, ScopeParts.saved_workflow),
    )
    saved_workflow_user = FunctionScope(
        label='<i class="fa-regular fa-person-rays"></i> User of Saved Workflow',
        parts=(
            ScopeParts.workspace,
            ScopeParts.saved_workflow,
            ScopeParts.platform_user,
        ),
    )

    deployment = FunctionScope(
        label=f'<img align="left" width="24" height="24" src="{icons.integrations_img}"> &nbsp; Deployed App',
        parts=(ScopeParts.workspace, ScopeParts.deployment),
    )
    deployment_user = FunctionScope(
        label='<i class="fa-solid fa-chalkboard-user"></i> User of Deployed App',
        parts=(ScopeParts.workspace, ScopeParts.deployment, ScopeParts.platform_user),
    )
    conversation = FunctionScope(
        label=f"{icons.chat} Chat Conversation",
        parts=(
            ScopeParts.workspace,
            ScopeParts.deployment,
            ScopeParts.platform_user,
            ScopeParts.conversation,
        ),
    )

    @classmethod
    def format_func(cls, name: str | None) -> str:
        scope = cls.get(name)
        if scope:
            return scope.label
        else:
            return '<span class="text-muted"><i class="fa-solid fa-shield-quartered"></i> Select Scope</span>'

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
