from app_users.models import AppUser
from bots.models import Platform, SavedRun
from gooey_gui.types.run_debug_info_props import DebugSource, RunDebugInfoProps
from gooey_gui.types.run_timeline_props import RunTimelineProps
from widgets.author import user_author, workspace_author
from widgets.workflow_cards import mask_user_id
from workspaces.models import Workspace


def run_debug_info_props(
    sr: SavedRun,
    *,
    run_by: AppUser | None,
    current_workspace: Workspace | None,
) -> RunDebugInfoProps:
    """The run metadata block at the top of the v2 Debug pane.

    `current_workspace` is the viewer's own workspace, or None when logged out, so the
    "charged to" link can fall back."""
    thread = sr.message_thread
    # run_time is measured by the worker from when it starts executing, and
    # updated_at is the final save, so the gap before that is the queue wait
    props = RunDebugInfoProps(
        timeline=RunTimelineProps(
            created_at=sr.created_at,
            started_at=sr.updated_at - sr.run_time,
            finished_at=sr.updated_at,
        )
    )

    if sr.platform is not None:
        platform = Platform(sr.platform)
        conversation = thread and thread.bot_conversation
        props.source = DebugSource(
            icon_html=platform.get_icon(),
            title=platform.get_title(),
            sender=conversation and mask_user_id(conversation.get_display_name() or ""),
        )

    if thread:
        props.conversation_title = thread.title or "Untitled conversation"
        # the last run is SET_NULL on delete, so the title may have no target
        if thread.last_run_id:
            props.conversation_url = thread.last_run.get_app_url()

    if sr.parent:
        props.parent_run_url = sr.parent.get_app_url()

    if run_by:
        props.run_by = user_author(run_by)

    if sr.workspace:
        props.charged_to = workspace_author(
            sr.workspace, current_workspace=current_workspace
        )

    return props
