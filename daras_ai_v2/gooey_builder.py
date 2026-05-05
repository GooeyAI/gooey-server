from __future__ import annotations

import typing

import gooey_gui as gui
from starlette.requests import Request

from bots.models import BotIntegration, SavedRun, db_msgs_to_api_json
from daras_ai_v2 import settings
from daras_ai_v2.web_widget_embed import load_web_widget_lib
from workspaces.models import Workspace

if typing.TYPE_CHECKING:
    from daras_ai_v2.base import BasePage

DEFAULT_GOOEY_BUILDER_PHOTO_URL = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/63bdb560-b891-11f0-b9bc-02420a00014a/generate-ai-abstract-symbol-artificial-intelligence-colorful-stars-icon-vector%201.jpg"


def render_gooey_builder_launcher(
    sidebar_key: str,
    request: Request,
    current_workspace: Workspace | None,
):
    if not can_launch_gooey_builder(request, current_workspace):
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


def render_gooey_builder(
    *,
    sidebar_key: str,
    request: Request,
    page: BasePage | None,
    current_workspace: Workspace | None,
):
    from daras_ai_v2.base import StateKeys, extract_model_fields

    if not can_launch_gooey_builder(request, current_workspace):
        return

    handle_update_gui_state(page)

    with gui.div(className="w-100 h-100"):
        render_gooey_builder_inline(
            sidebar_key=sidebar_key,
            page_slug=page.slug_versions[-1],
            builder_state=dict(
                status=dict(
                    error_msg=gui.session_state.get(StateKeys.error_msg),
                    run_status=gui.session_state.get(StateKeys.run_status),
                    run_time=gui.session_state.get(StateKeys.run_time),
                ),
                request=extract_model_fields(
                    model=page.RequestModel, state=gui.session_state
                ),
                response=extract_model_fields(
                    model=page.ResponseModel, state=gui.session_state
                ),
                metadata=dict(
                    title=page.current_pr.title,
                    description=page.current_pr.notes,
                ),
                run_id=page.current_sr.run_id,
                uid=page.current_sr.uid,
            ),
            sr=page.current_sr,
        )


def handle_update_gui_state(page: BasePage):
    from daras_ai_v2.workflow_url_input import url_to_runs

    update_gui_state: dict | None = gui.session_state.pop("update_gui_state", None)
    if not update_gui_state:
        return

    create_new_run: bool = update_gui_state.pop("create_new_run", True)
    gooey_builder_web_url: str | None = update_gui_state.pop(
        "gooey_builder_web_url", None
    )

    gui.session_state.update(update_gui_state)

    if not create_new_run:
        return
    sr = page.create_and_validate_new_run(enable_rate_limits=True, run_status=None)
    if not sr:
        return

    if gooey_builder_web_url:
        sr.parent_builder_saved_run = url_to_runs(gooey_builder_web_url)[1]
        sr.save(update_fields=["parent_builder_saved_run"])

    raise gui.RedirectException(sr.get_app_url())


def render_gooey_builder_inline(
    *, sidebar_key: str, page_slug: str, builder_state: dict, sr: SavedRun
):
    if not settings.GOOEY_BUILDER_INTEGRATION_ID:
        return

    bi = BotIntegration.objects.get(id=settings.GOOEY_BUILDER_INTEGRATION_ID)
    config = bi.get_web_widget_config(
        hostname="gooey.ai", target="#gooey-builder-embed"
    )

    config["mode"] = "inline"
    config["showRunLink"] = True
    config["showToolCalls"] = True
    config["enableSourcePreview"] = False
    branding = config.setdefault("branding", {})
    branding["showPoweredByGooey"] = False

    config.setdefault("payload", {}).setdefault("variables", {})
    # will be added later in the js code
    variables = dict(
        update_gui_state_params=dict(state=builder_state, page_slug=page_slug),
    )

    suppress_conversation_data = handle_widget_conversation_change()
    conversation_data = None
    if not suppress_conversation_data:
        conversation_data = get_conversation_data_for_saved_run(bi, sr)

    gui.div(style=dict(height="100%"), id="gooey-builder-embed")
    load_web_widget_lib()
    gui.js(
        GOOEY_BUILDER_INLINE_JS,
        config=config,
        variables=variables,
        sidebar_key=sidebar_key,
        conversation_data=conversation_data,
    )


GOOEY_BUILDER_INLINE_JS = (
    settings.BASE_DIR / "static/js/gooey_builder_inline_embed.js"
).read_text()


def can_launch_gooey_builder(
    request: Request, current_workspace: Workspace | None
) -> bool:
    if not settings.GOOEY_BUILDER_INTEGRATION_ID:
        return False
    if not request.user or request.user.is_anonymous:
        return False
    if request.user.is_admin():
        return True
    return current_workspace and current_workspace.enable_bot_builder


def get_conversation_data_for_saved_run(
    bot_builder_integration: BotIntegration, sr: SavedRun
) -> dict | None:
    """
    Returns conversation_data for the builder conversation associated with the given
    SavedRun (messages up to gooey_builder_last_message_id), or None if not found.
    """
    if not sr.parent_builder_saved_run:
        return None

    from bots.models.convo_msg import Message
    from routers.bots_api import api_hashids

    try:
        last_message = Message.objects.get(saved_run=sr.parent_builder_saved_run)
    except Message.DoesNotExist:
        return None

    conversation = last_message.conversation
    msgs_qs = conversation.messages.filter(created_at__lte=last_message.created_at)
    messages = list(
        db_msgs_to_api_json(msgs_qs.last_n_msgs(reset_at=conversation.reset_at))
    )
    data = dict(
        bot_id=api_hashids.encode(bot_builder_integration.id),
        user_id=conversation.web_user_id,
        timestamp=conversation.created_at.isoformat(),
        messages=messages,
    )
    # only send the conversation id for a full conversation,
    # for partial messages start a new conversation
    if last_message == conversation.messages.latest():
        data["id"] = api_hashids.encode(conversation.id)
    return data


def handle_widget_conversation_change() -> bool:
    from bots.models.convo_msg import Conversation
    from routers.bots_api import api_hashids

    conversation_id_hashed = gui.session_state.pop(
        "builder_selected_conversation", None
    )
    if not conversation_id_hashed:
        return False

    try:
        [conversation_id] = api_hashids.decode(conversation_id_hashed)
    except (IndexError, ValueError):
        return True

    try:
        conversation = Conversation.objects.get(id=conversation_id)
    except Conversation.DoesNotExist:
        return True

    # Find the lastest message whose builder run was associated with a child saved_run
    last_message = (
        conversation.messages.filter(
            saved_run__child_builder_saved_runs__isnull=False,
        )
        .order_by("-created_at")
        .select_related("saved_run")
        .first()
    )
    if not last_message:
        return True

    for child_sr in last_message.saved_run.child_builder_saved_runs.order_by().all():
        raise gui.RedirectException(child_sr.get_app_url())
    return True
