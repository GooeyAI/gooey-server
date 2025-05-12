import json

import gooey_gui as gui

from app_users.models import AppUser
from bots.models import PublishedRun
from daras_ai_v2 import icons, settings
from widgets.workflow_metadata_gen import (
    render_ai_generated_image_widget,
)
from workspaces.models import Workspace
from bots.models import Workflow

CIRCLE_IMAGE_WORKFLOWS = [Workflow.VIDEO_BOTS]


def render_workflow_photo_uploader(
    workspace: Workspace,
    user: AppUser,
    pr: PublishedRun,
    title: str,
    description: str,
    key: str = "photo_url",
) -> str:
    is_generating, error_msg = pull_icon_bot_result(key)
    photo_url = gui.session_state.setdefault(key, pr.photo_url) or ""
    with gui.div(
        className="d-flex gap-2 flex-md-column flex-row align-items-center h-100 pt-md-4 mt-md-2 pb-3 pb-md-0"
    ):
        pressed_generate = render_ai_generated_image_widget(
            image_url=photo_url,
            key=key,
            is_generating=is_generating,
            error_msg=error_msg,
            icon=icons.photo,
            is_circle_image=pr.workflow in CIRCLE_IMAGE_WORKFLOWS,
        )
    if pressed_generate:
        gui.session_state[key + ":bot-channel"] = run_icon_bot(
            workspace=workspace,
            user=user,
            title=title,
            description=description,
        )
        raise gui.RerunException()
    return photo_url


def render_change_notes_input(key: str):
    gui.html('<i class="fa-light fa-xl fa-money-check-pen mb-3"></i>')
    with gui.div(className="flex-grow-1"):
        return gui.text_input(
            "",
            key=key,
            placeholder="Add change notes",
        )


PROMPT_FORMAT = '''\
Title: %s 
Description: """
%s
"""
Respond with the following JSON object: {"icon_url": <generated icon url>, "error": <in case there was an error, provide an error message here>"}\
'''


def run_icon_bot(
    workspace: Workspace, user: AppUser, title: str, description: str
) -> str:
    from recipes.VideoBots import VideoBotsPage

    pr = VideoBotsPage.get_pr_from_example_id(example_id=settings.ICON_BOT_EXAMPLE_ID)
    result, sr = pr.submit_api_call(
        workspace=workspace,
        current_user=user,
        request_body=dict(
            input_prompt=PROMPT_FORMAT % (title, description),
            messages=[],
            response_format_type="json_object",
        ),
        deduct_credits=False,
    )
    return VideoBotsPage.realtime_channel_name(sr.run_id, sr.uid)


def pull_icon_bot_result(key: str) -> tuple[bool, str | None]:
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
        gui.session_state[key] = result.get("icon_url")
        error_msg = result.get("error")
    else:
        return True, error_msg

    gui.session_state.pop(key + ":bot-channel", None)
    return False, error_msg
