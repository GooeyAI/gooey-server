from __future__ import annotations

import json
import typing

import gooey_gui as gui
from furl import furl

from app_users.models import AppUser
from bots.models import BotIntegration, Platform
from bots.models.saved_run import SavedRun
from bots.models.workflow import Workflow, WorkflowAccessLevel
from daras_ai_v2 import icons, settings
from daras_ai_v2.copy_to_clipboard_button_widget import copy_to_clipboard_button
from widgets.workflow_metadata_gen import (
    render_ai_generated_image_widget,
)
from workspaces.models import Workspace

if typing.TYPE_CHECKING:
    from recipes.VideoBots import PublishedRun


def render_demo_buttons_header(pr: PublishedRun):
    demo_bots = get_demo_bots(pr)
    if not demo_bots:
        return
    with (
        gui.styled("& button { padding: 4px 12px !important }"),
        gui.div(className="d-flex gap-1 my-1"),
    ):
        for bi_id, platform in demo_bots:
            dialog_ref = gui.use_alert_dialog(key=f"demo-modal-{bi_id}")
            if render_demo_button(bi_id, platform, className="w-100"):
                dialog_ref.set_open(True)
            if dialog_ref.is_open:
                render_demo_dialog(dialog_ref, bi_id)


@gui.cache_in_session_state
def get_demo_bots(pr: PublishedRun):
    return list(
        BotIntegration.objects.filter(
            published_run=pr,
            public_visibility__gt=WorkflowAccessLevel.VIEW_ONLY,
        )
        .order_by("platform")
        .distinct("platform")
        .values_list("id", "platform")
    )


def render_demo_button(bi_id: int, platform_id: int, className: str = ""):
    platform = Platform(platform_id)
    label = f"{platform.get_icon()} {platform.get_title()}"
    className += " m-0"
    key = f"demo-button-{bi_id}"

    bg_color = platform.get_demo_button_color()
    if not bg_color:
        return gui.button(label, key=key, type="secondary", className=className)

    return gui.button(
        label,
        key=key,
        className=className,
        style={"backgroundColor": bg_color, "borderColor": bg_color, "color": "white"},
    )


def render_demo_dialog(ref: gui.AlertDialogRef, bi_id: int):
    bi = BotIntegration.objects.get(id=bi_id)
    platform = Platform(bi.platform)
    with gui.alert_dialog(
        ref,
        large=True,
        modal_title=(
            f"### {platform.get_icon()} {platform.get_title()} Demo\n"
            f"#### {bi.name or ''}"
        ),
        unsafe_allow_html=True,
    ):
        col1, col2 = gui.columns(2)
        with col1:
            render_demo_text(bi)

        if not bi.demo_qr_code_image:
            return

        with col2:
            with gui.div(className="d-flex align-items-center gap-2"):
                gui.caption("Or scan QR Code")
                gui.download_button(
                    label=icons.download_solid,
                    url=bi.demo_qr_code_image,
                    type="tertiary",
                    className="py-1",
                    unsafe_allow_html=True,
                )
            gui.image(src=bi.demo_qr_code_image)


def render_demo_text(bi: BotIntegration):
    if bi.platform == Platform.TWILIO:
        gui.caption("Call")
    else:
        gui.caption("Message")

    with gui.div(
        className="container-margin-reset d-flex align-items-center gap-2 mt-3"
    ):
        test_link = bi.get_bot_test_link()
        gui.write(
            f"[{bi.get_display_name()}]({test_link})",
            className="fs-5 fw-bold",
        )
        copy_to_clipboard_button(
            icons.copy_solid,
            value=test_link.lstrip("tel:"),
            type="tertiary",
            className="m-0",
        )

    if bi.platform == Platform.TWILIO:
        sms_url = furl("sms:") / bi.twilio_phone_number.as_e164
        if bi.extension_number:
            sms_url.args["body"] = f"{bi.extension_number}"
        gui.write(f"or [Send SMS]({sms_url})", className="fs-5 fw-bold")

    if bi.demo_notes:
        gui.write(bi.demo_notes, className="d-block mt-3")


def render_demo_button_settings(
    *, workspace: Workspace, user: AppUser, bi: BotIntegration
) -> None:
    with (
        gui.styled("""
        @media (min-width: 768px) {
            & {
                max-width: 55%;
            }
        }
        """),
        gui.div(),
    ):
        enabled = bi.public_visibility > WorkflowAccessLevel.VIEW_ONLY
        new_value = gui.switch(
            "###### Show Demo Button",
            value=enabled,
        )
        gui.caption("Add 'Try Demo' to connected Copilot page")
        if new_value != enabled:
            enabled = new_value
            if enabled:
                bi.public_visibility = WorkflowAccessLevel.FIND_AND_VIEW
            else:
                bi.public_visibility = WorkflowAccessLevel.VIEW_ONLY

        if not enabled:
            return

    col1, col2 = gui.columns(2)

    with col1:
        gui.write("###### Demo Notes")
        bi.demo_notes = gui.text_area(
            "",
            placeholder="Add demo instructions as text or markdown",
            value=bi.demo_notes,
        )

    with col2:
        qr_code_settings(workspace=workspace, user=user, bi=bi)


def qr_code_settings(
    *,
    workspace: Workspace,
    user: AppUser,
    bi: BotIntegration,
    key: str = "demo_qr_code_image",
):
    is_generating, error_msg = pull_qr_bot_result(key)

    bi.demo_qr_code_image = (
        gui.session_state.setdefault(key, bi.demo_qr_code_image) or ""
    )
    if not bi.demo_qr_code_image:
        bi.demo_qr_code_run = None
    else:
        bi.demo_qr_code_run_id = gui.session_state.setdefault(
            key + ":run_id", bi.demo_qr_code_run_id
        )

    gui.write(
        "###### Demo QR Code",
        help="Generate or upload a scannable QR Code for users to access the integration",
    )

    with gui.div(className="d-flex gap-2 flex-row align-items-center mb-3"):
        pressed_generate = render_ai_generated_image_widget(
            image_url=bi.demo_qr_code_image,
            key=key,
            is_generating=is_generating,
            error_msg=error_msg,
            icon=icons.photo,  # You can replace with a QR icon if available
        )
    if pressed_generate:
        gui.session_state[key + ":bot-channel"] = run_qr_bot(
            workspace=workspace,
            user=user,
            bi=bi,
            key=key,
        )
        raise gui.RerunException()

    if bi.demo_qr_code_run:
        with gui.link(
            to=bi.demo_qr_code_run.get_app_url(),
            target="_blank",
        ):
            gui.caption("View QR Generation Run")


PROMPT_FORMAT = '''\
Title: """%s"""
Description: """
%s
"""
qr_code_data: %s

Respond with the following JSON object: {"qr_code_url": <generated image url>, "error": <in case there was an error, provide an error message here>"}\
'''


def run_qr_bot(
    workspace: Workspace, user: AppUser, bi: BotIntegration, key: str
) -> str:
    from recipes.VideoBots import VideoBotsPage

    prompt = PROMPT_FORMAT % (
        bi.name or (bi.published_run_id and bi.published_run.title),
        bi.descripton or (bi.published_run_id and bi.published_run.notes),
        bi.get_bot_test_link(),
    )
    pr = VideoBotsPage.get_pr_from_example_id(example_id=settings.QR_BOT_EXAMPLE_ID)
    result, sr = pr.submit_api_call(
        workspace=workspace,
        current_user=user,
        request_body=dict(
            input_prompt=prompt,
            messages=[],
            response_format_type="json_object",
        ),
        deduct_credits=False,
    )
    gui.session_state[key + ":bot_run_id"] = sr.id
    return VideoBotsPage.realtime_channel_name(sr.run_id, sr.uid)


def pull_qr_bot_result(key: str) -> tuple[bool, str | None]:
    """
    Pulls the result from the QR bot and updates the session state with the result.
    Returns a tuple of (success, error_msg).
    """
    from daras_ai_v2.base import RecipeRunState, StateKeys
    from recipes.VideoBots import VideoBotsPage

    channel = gui.session_state.get(key + ":bot-channel")
    error_msg = None
    if not channel:
        return False, error_msg

    state = gui.realtime_pull([channel])[0]
    recipe_run_state = state and VideoBotsPage.get_run_state(state)
    match recipe_run_state:
        case RecipeRunState.failed:
            error_msg = state.get(StateKeys.error_msg)
        case RecipeRunState.completed:
            result = json.loads(state.get("output_text", ["{}"])[0])
            image_url = result.get("qr_code_url")
            gui.session_state[key] = image_url
            error_msg = result.get("error")
            bot_run_id = gui.session_state.pop(key + ":bot_run_id", None)
            if bot_run_id:
                gui.session_state[key + ":run_id"] = (
                    SavedRun.objects.filter(
                        called_by_runs__saved_run_id=bot_run_id,
                        workflow=Workflow.QR_CODE,
                    )
                    .values_list("id", flat=True)
                    .first()
                )
        case _:
            return True, error_msg

    gui.session_state.pop(key + ":bot-channel", None)
    return False, error_msg
