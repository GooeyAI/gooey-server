from __future__ import annotations

import typing

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
from daras_ai_v2.breadcrumbs import get_title_breadcrumbs
from daras_ai_v2.fastapi_tricks import fastapi_login_required
from daras_ai_v2.web_widget_embed import (
    load_chat_widget_lib,
    chat_widget_input_to_request_body,
    get_chat_widget_messages,
    get_builder_conversation_messages,
)
from routers.custom_api_router import CustomAPIRouter

from workspaces.models import Workspace
from workspaces.widgets import get_current_workspace

if typing.TYPE_CHECKING:
    from daras_ai_v2.base import BasePage

DEFAULT_GOOEY_BUILDER_PHOTO_URL = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/63bdb560-b891-11f0-b9bc-02420a00014a/generate-ai-abstract-symbol-artificial-intelligence-colorful-stars-icon-vector%201.jpg"


def render_gooey_builder_launcher(
    sidebar_key: str,
    request: fastapi.Request,
    workspace: Workspace | None,
):
    if not can_launch_gooey_builder(request, workspace):
        return

    try:
        bi = BotIntegration.objects.get(id=settings.GOOEY_BUILDER_INTEGRATION_ID)
    except BotIntegration.DoesNotExist:
        return
    branding = bi.get_web_widget_branding()
    photo_url = branding.get("photoUrl", DEFAULT_GOOEY_BUILDER_PHOTO_URL)

    with gui.styled("& button:hover { scale: 1.2; }"):
        with gui.div(
            className="position-fixed d-none d-xxl-block",
            style={"bottom": "24px", "left": "16px", "zIndex": "99"},
        ):
            with gui.tag(
                "button",
                type="button",
                className=f"btn btn-secondary border-0 p-0 {sidebar_key}-button",
                onClick=f"window.dispatchEvent(new CustomEvent(`{sidebar_key}:open`))",
                style={
                    "width": "56px",
                    "height": "56px",
                    "borderRadius": "50%",
                    "boxShadow": "#0000001a 0 1px 4px, #0003 0 2px 12px",
                },
            ):
                gui.html(
                    f"<img src='{photo_url}' style='width: 56px; height: 56px; border-radius: 50%;' />"
                )

    with gui.tag(
        "button",
        type="button",
        className=f"border-0 m-0 btn btn-secondary rounded-pill d-xxl-none p-0 {sidebar_key}-button",
        onClick=f"window.dispatchEvent(new CustomEvent(`{sidebar_key}:open`))",
        style={
            "width": "36px",
            "height": "36px",
            "borderRadius": "50%",
        },
    ):
        gui.html(
            f"<img src='{photo_url}' style='width: 36px; height: 36px; border-radius: 50%;' />"
        )


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
    bi = BotIntegration.objects.select_related("published_run").get(
        id=settings.GOOEY_BUILDER_INTEGRATION_ID
    )
    config = bi.get_web_widget_config(
        hostname="gooey.ai", target="#gooey-builder-embed"
    )

    config["integration_id"] = "magic"
    config["mode"] = "inline"
    config["showRunLink"] = True
    config["showToolCalls"] = True
    config["enableSourcePreview"] = False
    config["enableConversations"] = True
    branding = config.setdefault("branding", {})
    branding["showPoweredByGooey"] = False

    builder_sr = page.current_sr.parent_builder_saved_run

    redirect_url = builder_sr and builder_sr.redirect_url
    if redirect_url:
        builder_sr.redirect_url = ""
        builder_sr.save(update_fields=["redirect_url"])
        raise gui.RedirectException(redirect_url)

    # `messages` drives the live (streaming) chat display and must come from the
    # builder run's own state. `conversation_messages` rides alongside it, carrying
    # each turn's point-in-time URLs (saved_run_url / builder_run_url) so the widget
    # can render a "go back to this turn" link per message -- consumed by a follow-up
    # change in the gooey-web-widget repo. It is metadata only; it never drives the
    # display, so it cannot regress streaming.
    conversation_messages = []
    if builder_sr and not gui.session_state.get("builderOnNewConversation"):
        builder_run_url = builder_sr.get_app_url()
        messages = get_chat_widget_messages(
            builder_sr.to_dict(), web_url=builder_sr.get_app_url()
        )
        if page.current_sr.conversation_id:
            conversation_messages = get_builder_conversation_messages(
                page.current_sr.conversation
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
        conversation_messages=conversation_messages,
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
    workflow_page_cls, prev_child, workflow_pr = url_to_runs(body.workflow_url)
    workflow_sr = prev_child.clone(
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

    from bots.models import RunConversation

    # The widget always sends *some* builder_run_url, so bool() can't tell new from
    # continue. It resolves to the published/default builder run for a fresh
    # conversation, or to a specific prior builder turn when continuing -- so
    # comparing the resolved run against the published template is the real signal.
    is_continuation = builder_sr != builder_pr.saved_run
    RunConversation.attach_run(
        sr=workflow_sr,
        parent_sr=prev_child,
        is_continuation=is_continuation,
        surface=SavedRun.Surface.builder_child,
        title=request_body.get("input_prompt") or "",
    )

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
    # Optional workflow filter. None lists builder conversations across all workflows.
    workflow: int | None = None

class WidgetRunMetadata(pydantic.BaseModel):
    title: str
    icon: str | None = None
    emoji: str | None = None


class WidgetConversation(pydantic.BaseModel):
    title: str
    timestamp: str
    url: str
    run_metadata: WidgetRunMetadata | None = None

@router.post(
    "/__/gooey-builder/fetch-conversations", dependencies=[fastapi_login_required]
)
def fetch_builder_conversations(
    request: fastapi.Request, body: FetchConversations
) -> list[WidgetConversation]:
    from bots.models import RunConversation

    qs = RunConversation.objects.for_listing(
        workspace=get_current_workspace(request.user, request.session),
        surface=SavedRun.Surface.builder_child,
        uid=request.user.uid,
    ).order_by("-updated_at")[: body.limit]
    return export_run_conversations(qs, include_run_metadata=True)


@router.post("/__/agent/fetch-conversations", dependencies=[fastapi_login_required])
def fetch_chat_conversations(
    request: fastapi.Request, body: FetchConversations
) -> list[WidgetConversation]:
    from bots.models import RunConversation
    from daras_ai_v2.workflow_url_input import url_to_runs

    try:
        pr = url_to_runs(body.run_url)[2]
    except (AssertionError, KeyError):
        return []
    if not pr:
        return []
    # One row per playground conversation of this published agent. A conversation
    # belongs to `pr` when its latest turn does (all turns share the same pr).
    qs = (
        RunConversation.objects.for_listing(
            workflow=Workflow.VIDEO_BOTS,
            workspace=get_current_workspace(request.user, request.session),
            surface=SavedRun.Surface.run,
        )
        .filter(last_run__parent_version__published_run=pr)
        .order_by("-updated_at")[: body.limit]
    )
    return export_run_conversations(qs)


def export_run_conversations(
    qs, include_run_metadata: bool = False
) -> list[WidgetConversation]:
    return [
        _export_run_conversation(convo, include_run_metadata)
        for convo in qs.select_related("last_run__parent_version__published_run")
    ]


def _export_run_conversation(
    convo, include_run_metadata: bool = False
) -> WidgetConversation:
    sr = convo.last_run
    pr = sr and sr.parent_published_run()
    result = WidgetConversation(
        title=convo.title or "",
        timestamp=convo.updated_at.isoformat(),
        url=sr.get_app_url() if sr else "",
    )
    if include_run_metadata:
        result.run_metadata = WidgetRunMetadata(
            title=_last_run_title(sr, pr),
            icon=_last_run_photo(sr, pr),
            emoji=Workflow(sr.workflow).emoji if sr else None,
        )
    return result


def _last_run_title(sr: SavedRun | None, pr: PublishedRun | None) -> str:
    """Latest turn's title without its surface prefix (e.g. "My Bot", not "Web Chat: My Bot")."""
    if not sr:
        return ""
    return get_title_breadcrumbs(Workflow(sr.workflow).page_cls, sr, pr).h1_title.title


def _last_run_photo(sr: SavedRun | None, pr: PublishedRun | None) -> str:
    """The workflow image shown in the page header -- the bot's photo, else the workflow default."""
    if not sr:
        return ""
    if pr and pr.photo_url:
        return pr.photo_url
    return Workflow(sr.workflow).get_or_create_metadata().default_image or ""
