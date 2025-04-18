import json

import gooey_gui as gui

from app_users.models import AppUser
from bots.models import PublishedRun
from daras_ai_v2 import icons, settings
from workspaces.models import Workspace


def render_workflow_photo_uploader(
    workspace: Workspace,
    user: AppUser,
    pr: PublishedRun,
    title: str,
    description: str,
    key: str = "photo_url",
) -> str:
    is_generating, error_msg = pull_icon_bot_result(key)

    if error_msg:
        error_dialog_ref = gui.use_alert_dialog(key=key + ":error-dialog")
        with gui.alert_dialog(ref=error_dialog_ref, modal_title="### Error"):
            with gui.tag("code"):
                gui.write(error_msg, className="text-danger")
            gui.write("Please try again or upload a photo manually.")

    photo_url = gui.session_state.setdefault(key, pr.photo_url) or ""

    upload_dialog_ref = gui.use_alert_dialog(key=key + ":upload-dialog")
    if photo_url:
        upload_dialog_ref.set_open(False)
    if upload_dialog_ref.is_open:
        with gui.alert_dialog(
            ref=upload_dialog_ref, modal_title="### Upload Workflow Image"
        ):
            gui.file_uploader("", accept=["image/*"], key=key)

    with gui.div(
        className="d-flex gap-2 flex-md-column flex-row align-items-center h-100 pt-md-4 mt-md-2 pb-3 pb-md-0"
    ):
        with workflow_photo_div(photo_url):
            if is_generating:
                with gui.styled(
                    """
                    &.generating_workflow_photo_spinner i {
                        animation: spin 0.7s ease-in-out infinite;
                    }
                    @keyframes spin {
                        0% { transform: rotate(0deg); }
                        100% { transform: rotate(360deg); }
                    }
                    """
                ):
                    gui.write(
                        f"## {icons.stars}",
                        className="text-muted generating_workflow_photo_spinner",
                        unsafe_allow_html=True,
                    )
            elif not photo_url:
                gui.write(
                    f"# {icons.photo}", className="text-muted", unsafe_allow_html=True
                )

        with gui.div(
            className="d-flex align-items-center justify-content-center gap-1 flex-md-row flex-column"
        ):
            if is_generating:
                gui.button(
                    f"{icons.sparkles} Generating...",
                    type="tertiary",
                    disabled=True,
                )
            elif photo_url:
                if gui.button(f"{icons.clear} Clear", type="tertiary"):
                    gui.session_state[key] = ""
                    raise gui.RerunException()
            else:
                if gui.button(f"{icons.upload} Upload", type="tertiary"):
                    upload_dialog_ref.set_open(True)
                    raise gui.RerunException()

                if gui.button(f"{icons.sparkles} Generate", type="tertiary"):
                    gui.session_state[key + ":icon-bot-channel"] = run_icon_bot(
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


def workflow_photo_div(url: str | None):
    return gui.div(
        style=dict(
            aspectRatio="1",
            width="80%",
            backgroundImage=f"url({url})" if url else "none",
            backgroundSize="cover",
            backgroundPosition="center",
        ),
        className="d-flex align-items-center justify-content-center p-5 bg-light b-1 border rounded",
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

    channel = gui.session_state.get(key + ":icon-bot-channel")
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
    gui.session_state.pop(key + ":icon-bot-channel", None)
    return False, error_msg
