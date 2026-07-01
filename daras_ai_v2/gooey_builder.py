from __future__ import annotations

import typing
from typing import Any

from django.db.models import F
import pydantic

from bots.models.workflow import Workflow
import gooey_gui as gui
import fastapi

from bots.models import (
    BotIntegration,
    SavedRun,
    PublishedRun,
)
from daras_ai_v2 import settings
from daras_ai_v2.fastapi_tricks import fastapi_login_required
from daras_ai_v2.web_widget_embed import (
    load_chat_widget_lib,
    chat_widget_input_to_request_body,
    get_chat_widget_messages,
)
from routers.custom_api_router import CustomAPIRouter

from workspaces.models import Workspace
from workspaces.widgets import get_current_workspace

if typing.TYPE_CHECKING:
    from daras_ai_v2.base import BasePage

DEFAULT_GOOEY_BUILDER_PHOTO_URL = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/63bdb560-b891-11f0-b9bc-02420a00014a/generate-ai-abstract-symbol-artificial-intelligence-colorful-stars-icon-vector%201.jpg"


class GooeyBuilderWorkflow(typing.TypedDict):
    current_url: str
    current_user: str
    current_workspace: str
    state: dict


def render_gooey_builder(
    *,
    sidebar_key: str,
    request: fastapi.Request,
    page: BasePage,
):
    if not can_launch_gooey_builder(request, page.current_workspace):
        return
    if not settings.GOOEY_BUILDER_INTEGRATION_ID:
        return
    bi = BotIntegration.objects.get(id=settings.GOOEY_BUILDER_INTEGRATION_ID)
    config = bi.get_web_widget_config(
        hostname="gooey.ai", target="#gooey-builder-embed"
    )

    config["integration_id"] = "magic"
    config["mode"] = "inline"
    config["showRunLink"] = True
    config["showToolCalls"] = True
    config["enableSourcePreview"] = False
    config["enableConversations"] = False
    branding = config.setdefault("branding", {})
    branding["showPoweredByGooey"] = False

    builder_sr = page.current_sr.parent_builder_saved_run

    redirect_url = builder_sr and builder_sr.redirect_url
    if redirect_url:
        builder_sr.redirect_url = ""
        builder_sr.save(update_fields=["redirect_url"])
        raise gui.RedirectException(redirect_url)

    if builder_sr and not gui.session_state.get("builderOnNewConversation"):
        builder_run_url = builder_sr.get_app_url()
        messages = get_chat_widget_messages(
            builder_sr.to_dict(), web_url=builder_sr.get_app_url()
        )
    else:
        builder_run_url = bi.published_run.get_app_url()
        messages = []

    load_chat_widget_lib()
    gui.component(
        "GooeyBuilderInlineEmbed",
        config=config,
        sidebar_key=sidebar_key,
        messages=messages,
        builder_run_url=builder_run_url,
        workflow_state={
            field_name: gui.session_state[field_name]
            for field_name in page.fields_to_save()
            if field_name in gui.session_state
        },
    )


def can_launch_gooey_builder(
    request: fastapi.Request, current_workspace: Workspace | None
) -> bool:
    if not settings.GOOEY_BUILDER_INTEGRATION_ID:
        return False
    if not request.user or request.user.is_anonymous:
        return False
    return True
    # if request.user.is_admin():
    #     return True
    # return current_workspace and current_workspace.enable_bot_builder


router = CustomAPIRouter()


class GooeyBuilderSendMessage(pydantic.BaseModel):
    workflow_url: str
    builder_run_url: str | None = None
    input_data: dict | None = None
    workflow_state: dict = {}


@router.post("/__/gooey-builder/send-message", dependencies=[fastapi_login_required])
def gooey_builder_send_message(request: fastapi.Request, body: GooeyBuilderSendMessage):
    from daras_ai_v2.workflow_url_input import url_to_runs
    from functions.gooey_builder_tools import insert_gooey_builder_variables

    workspace = get_current_workspace(request.user, request.session)

    # copy the workflow_url into a new run linked to
    # builder_sr so the chat widget can navigate the user to a workflow page
    # that knows which builder iteration produced it
    workflow_page_cls, workflow_sr, workflow_pr = url_to_runs(body.workflow_url)
    workflow_sr = workflow_sr.clone(
        parent_pr=workflow_pr,
        uid=request.user.uid,
        workspace_id=workspace.id,
        surface=SavedRun.Surface.builder_child,
    )
    workflow_sr.state.update(body.workflow_state)
    workflow_sr.save()

    workflow_url = workflow_sr.get_app_url()
    builder_run_url = body.builder_run_url or get_default_builder_pr().get_app_url()
    builder_page_cls, builder_sr, builder_pr = url_to_runs(builder_run_url)
    request_body = chat_widget_input_to_request_body(
        builder_sr.state, body.input_data or builder_sr.state
    )
    insert_gooey_builder_variables(request_body, workflow_url)

    workflow_sr.parent_builder_saved_run = builder_pr.submit_api_call(
        current_user=request.user,
        workspace=workspace,
        request_body=request_body,
        surface=SavedRun.Surface.builder_prompt,
    )[1]
    workflow_sr.save(update_fields=["parent_builder_saved_run"])

    return workflow_url


def get_default_builder_pr() -> PublishedRun:
    try:
        bi = BotIntegration.objects.get(id=settings.GOOEY_BUILDER_INTEGRATION_ID)
    except BotIntegration.DoesNotExist:
        raise fastapi.HTTPException(
            status_code=404,
            detail="gooey builder deployment not found",
        )
    return bi.published_run


class FetchConversations(pydantic.BaseModel):
    run_url: str
    limit: int = 50


@router.post(
    "/__/gooey-builder/fetch-conversations", dependencies=[fastapi_login_required]
)
def fetch_builder_conversations(
    request: fastapi.Request, body: FetchConversations
) -> list[dict]:
    qs = (
        SavedRun.objects.filter(
            uid=request.user.uid,
            workspace=get_current_workspace(request.user, request.session),
            surface=SavedRun.Surface.builder_child,
        )
        .annotate(title=F("parent_builder_saved_run__state__input_prompt"))
        .order_by("-updated_at")[: body.limit]
    )
    return export_chat_qs(qs)


@router.post("/__/agent/fetch-conversations", dependencies=[fastapi_login_required])
def fetch_chat_conversations(
    request: fastapi.Request, body: FetchConversations
) -> list[dict]:
    from daras_ai_v2.workflow_url_input import url_to_runs

    try:
        pr = url_to_runs(body.run_url)[2]
    except (AssertionError, KeyError):
        return []
    if not pr:
        return []
    qs = (
        SavedRun.objects.filter(
            workflow=Workflow.VIDEO_BOTS,
            workspace=get_current_workspace(request.user, request.session),
            parent_version__published_run=pr,
        )
        .annotate(title=F("state__input_prompt"))
        .order_by("-updated_at")[: body.limit]
    )
    return export_chat_qs(qs)


def export_chat_qs(qs) -> list[dict[str, Any]]:
    return [
        dict(
            title=sr.title or "",
            timestamp=sr.updated_at.isoformat(),
            url=sr.get_app_url(),
        )
        for sr in qs
    ]
