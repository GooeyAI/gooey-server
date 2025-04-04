import gooey_gui as gui

from app_users.models import AppUser
from bots.models import PublishedRun, PublishedRunPermission
from widgets.author import render_author_from_workspace
from workspaces.models import Workspace
from workspaces.views import member_invite_button_with_dialog


def render_workspace_with_invite_button(workspace: Workspace, user_id: int) -> None:
    """
    Renders a workspace with an invite button in a two-column layout.

    Args:
        workspace: The workspace to render
        user_id: The ID of the current user
    """
    col1, col2 = gui.columns([9, 3], responsive=False)
    with col1:
        with gui.tag("p", className="mb-1 text-muted"):
            gui.html("WORKSPACE")
        render_author_from_workspace(workspace)
    with col2:
        try:
            membership = workspace.memberships.get(user_id=user_id)
        except Workspace.DoesNotExist:
            return
        member_invite_button_with_dialog(
            membership,
            close_on_confirm=False,
            type="tertiary",
            className="mb-0",
        )


def render_share_options_for_team_workspace(
    user: AppUser,
    pr: PublishedRun,
) -> dict[str, PublishedRunPermission]:
    with gui.div(className="mb-4"):
        render_workspace_with_invite_button(pr.workspace, user.id)

    # we check for same privilege level for "sharing" as "deletion"
    # because share-settings can be used to hide the published run
    can_user_edit = PublishedRunPermission.can_user_delete_published_run(
        workspace=pr.workspace,
        user=user,
        pr=pr,
    )

    updates = {}
    options = {
        str(perm.value): perm.get_team_sharing_text(pr, current_user=user)
        for perm in PublishedRunPermission.get_team_sharing_options(
            pr, current_user=user
        )
    }

    with gui.div(className="mb-4"):
        updates["team_permission"] = PublishedRunPermission(
            int(
                gui.radio(
                    "",
                    options=options,
                    format_func=options.__getitem__,
                    key="published-run-team-permission",
                    value=str(pr.team_permission),
                    disabled=not can_user_edit,
                )
            )
        )

    if can_user_edit and pr.workspace.can_have_private_published_runs():
        is_public = gui.checkbox(
            label=PublishedRunPermission.CAN_FIND.get_public_sharing_text(pr),
            value=(pr.visibility == PublishedRunPermission.CAN_FIND.value),
            disabled=(updates["team_permission"] == PublishedRunPermission.CAN_VIEW),
        )
        if is_public and updates["team_permission"] != PublishedRunPermission.CAN_VIEW:
            updates["visibility"] = PublishedRunPermission.CAN_FIND
        else:
            updates["visibility"] = PublishedRunPermission.CAN_VIEW
    elif pr.visibility == PublishedRunPermission.CAN_FIND:
        gui.write(
            PublishedRunPermission.CAN_FIND.get_public_sharing_text(pr=pr),
            unsafe_allow_html=True,
        )

    if can_user_edit:
        return updates
    else:
        return {}
