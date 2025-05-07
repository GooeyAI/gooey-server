from __future__ import annotations

import json
import typing

import gooey_gui as gui

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
        gui.styled("& button { padding: 4px !important }"),
        gui.div(className="d-flex flex-column justify-content-center gap-1 my-1"),
    ):
        with gui.div(className="container-margin-reset text-center w-100 text-nowrap"):
            gui.caption("Try the demo")
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
        ).values_list("id", "platform")
    )


def render_demo_button(bi_id: int, platform_id: int, className: str = ""):
    platform = Platform(platform_id)
    label = f"{platform.get_icon()} {platform.get_title()}"
    className += " px-3 py-2 m-0"
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
            gui.caption("Message")
            with gui.div(className="d-flex align-items-center gap-2 mt-3"):
                gui.write(
                    f"[{bi.get_display_name()}]({bi.get_bot_test_link()})",
                    className="fs-5 fw-bold",
                )
                copy_to_clipboard_button(
                    icons.copy_solid,
                    value=bi.get_bot_test_link(),
                    type="tertiary",
                )
            if bi.demo_notes:
                gui.write(bi.demo_notes, className="d-block mt-3")

        if not bi.demo_qr_code_image:
            return

        with col2:
            with gui.div(className="d-flex align-items-center gap-2"):
                gui.caption("Or scan QR Code")
                gui.anchor(
                    label=icons.download_solid,
                    href=bi.get_bot_test_link(),
                    type="tertiary",
                    unsafe_allow_html=True,
                    className="py-1",
                )
            gui.image(src=bi.demo_qr_code_image)


def render_demo_button_settings(
    *, workspace: Workspace, user: AppUser, bi: BotIntegration
) -> None:
    col1, col2 = gui.columns(2, responsive=False)
    with col1:
        gui.write("###### Show Demo Button")
        gui.caption('Add "Try Demo" to connected Copilot page')
    with col2:
        enabled = bi.public_visibility > WorkflowAccessLevel.VIEW_ONLY
        new_value = gui.switch("", value=enabled)
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
            "", placeholder="Add demo instructions as text or markdown"
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
    elif gui.session_state.get(key + ":qr_bot_run_id"):
        bi.demo_qr_code_run = SavedRun.objects.filter(
            called_by_runs__saved_run_id=gui.session_state.pop(key + ":qr_bot_run_id"),
            workflow=Workflow.QR_CODE,
        ).first()

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

Respond with the following JSON object: {"qr_code_url": <generated image url>, "run_url": , "error": <in case there was an error, provide an error message here>"}\
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
    gui.session_state[key + ":qr_bot_run_id"] = sr.id
    return VideoBotsPage.realtime_channel_name(sr.run_id, sr.uid)


def pull_qr_bot_result(key: str) -> tuple[bool, str | None]:
    from daras_ai_v2.base import RecipeRunState, StateKeys
    from recipes.VideoBots import VideoBotsPage

    channel = gui.session_state.get(key + ":bot-channel")
    error_msg = None
    if not channel:
        return False, error_msg

    state = gui.realtime_pull([channel])[0]
    recipe_run_state = state and VideoBotsPage.get_run_state(state)
    if recipe_run_state == RecipeRunState.failed:
        error_msg = state.get(StateKeys.error_msg)
    elif recipe_run_state == RecipeRunState.completed:
        result = json.loads(state["output_text"][0])
        image_url = result.get("qr_code_url")
        gui.session_state[key] = image_url
        error_msg = result.get("error")
    else:
        return True, error_msg

    gui.session_state.pop(key + ":bot-channel", None)
    return False, error_msg
