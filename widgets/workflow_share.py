import gooey_gui as gui

from app_users.models import AppUser
from bots.models import PublishedRun, WorkflowAccessLevel, SavedRun
from daras_ai_v2 import icons
from daras_ai_v2.copy_to_clipboard_button_widget import copy_to_clipboard_button
from daras_ai_v2.fastapi_tricks import get_route_path
from routers.account import account_route
from widgets.author import render_author_from_workspace
from widgets.publish_form import clear_publish_form
from workspaces.models import Workspace, WorkspaceMembership
from workspaces.views import member_invite_button_with_dialog
from workspaces.widgets import render_create_workspace_alert


def render_share_button(
    publish_dialog_ref: gui.AlertDialogRef,
    workspace_id: int | None,
    user: AppUser | None,
    sr: SavedRun,
    pr: PublishedRun,
    current_app_url: str,
    session: dict,
) -> None:
    if (
        not pr.is_root()
        and pr.saved_run_id == sr.id
        and user
        and (user.is_admin() or workspace_id == pr.workspace_id)
    ):
        dialog = gui.use_alert_dialog(key="share-modal")
        icon = pr.get_share_icon()
        if gui.button(
            f'{icon} <span class="d-none d-lg-inline">Share</span>',
            className="mb-0 px-2 px-lg-4",
        ):
            dialog.set_open(True)
        if dialog.is_open:
            render_share_modal(
                dialog=dialog,
                publish_dialog_ref=publish_dialog_ref,
                user=user,
                pr=pr,
                current_app_url=current_app_url,
                session=session,
            )
    else:
        copy_to_clipboard_button(
            label=icons.link,
            value=current_app_url,
            type="secondary",
            className="mb-0 px-2",
        )


def render_share_modal(
    dialog: gui.AlertDialogRef,
    publish_dialog_ref: gui.AlertDialogRef,
    user: AppUser,
    pr: PublishedRun,
    current_app_url: str,
    session: dict,
):
    # modal is only valid for logged in users
    assert user and pr.workspace

    with gui.alert_dialog(ref=dialog, modal_title=f"#### Share: {pr.title}"):
        with gui.styled("& .gui-input-radio { display: flex; align-items: center; }"):
            if not pr.workspace.is_personal:
                updates = render_share_options_for_team_workspace(user=user, pr=pr)
            else:
                updates = render_share_options_for_personal_workspace(pr=pr)

        changed = any(getattr(pr, k) != v for k, v in updates.items())
        if changed:
            pr.add_version(
                user=user,
                saved_run=pr.saved_run,
                title=pr.title,
                notes=pr.notes,
                public_access=updates.get("public_access"),
                workspace_access=updates.get("workspace_access"),
                change_notes="Share settings updated",
            )

        workspaces = user.cached_workspaces
        if pr.workspace.is_personal and len(workspaces) == 1:
            render_create_workspace_alert()
        elif pr.workspace.is_personal and len(workspaces) > 1:
            with gui.div(
                className="alert alert-warning mb-0 mt-4 d-flex align-items-baseline"
            ):
                duplicate = gui.button(
                    f"{icons.fork} Duplicate",
                    type="link",
                    className="d-inline m-0 p-0",
                )
                gui.html("&nbsp;" + "this workflow to edit with others")
                if duplicate:
                    clear_publish_form()
                    gui.session_state["published_run_workspace"] = workspaces[-1].id
                    publish_dialog_ref.set_open(True)
                if publish_dialog_ref.is_open:
                    return
        elif (
            pr.public_access == WorkflowAccessLevel.FIND_AND_VIEW
            and not pr.workspace.is_personal
            and not pr.workspace.can_have_private_published_runs()
            and user in pr.workspace.get_admins()
        ):
            with gui.div(
                className="alert alert-warning mb-0 mt-4 d-flex align-items-baseline container-margin-reset"
            ):
                gui.write(
                    f"{icons.company_solid} [Upgrade]({get_route_path(account_route)}) to make your team & workflows **private**.",
                    unsafe_allow_html=True,
                )

        with gui.div(className="d-flex justify-content-between mt-4"):
            copy_to_clipboard_button(
                label=f"{icons.link} Copy Link",
                value=current_app_url,
                type="secondary",
                className="py-2 px-3 m-0",
            )
            if gui.button("Done", type="primary", className="py-2 px-5 m-0"):
                dialog.set_open(False)
                gui.rerun()


def render_share_options_for_team_workspace(
    user: AppUser, pr: PublishedRun
) -> dict[str, WorkflowAccessLevel]:
    with gui.div(className="mb-4"):
        render_workspace_with_invite_button(pr.workspace, user.id)

    # we check for same privilege level for "sharing" as "deletion"
    # because share-settings can be used to hide the published run
    can_user_edit = WorkflowAccessLevel.can_user_delete_published_run(
        workspace=pr.workspace,
        user=user,
        pr=pr,
    )

    updates = {}
    options = {
        str(perm.value): perm.get_team_sharing_text(pr, current_user=user)
        for perm in WorkflowAccessLevel.get_team_sharing_options(pr, current_user=user)
    }

    with gui.div(className="mb-4"):
        updates["workspace_access"] = WorkflowAccessLevel(
            int(
                gui.radio(
                    "",
                    options=options,
                    format_func=options.__getitem__,
                    key="published-run-team-permission",
                    value=str(pr.workspace_access),
                    disabled=not can_user_edit,
                )
            )
        )

    if can_user_edit and pr.workspace.can_have_private_published_runs():
        is_disabled = updates["workspace_access"] == WorkflowAccessLevel.VIEW_ONLY
        if is_disabled:
            gui.session_state["workflow-is-public"] = False
        is_public = gui.checkbox(
            label=WorkflowAccessLevel.FIND_AND_VIEW.get_public_sharing_text(pr),
            key="workflow-is-public",
            value=(
                not is_disabled
                and pr.public_access == WorkflowAccessLevel.FIND_AND_VIEW.value
            ),
            disabled=is_disabled,
        )
        if is_public:
            updates["public_access"] = WorkflowAccessLevel.FIND_AND_VIEW
        else:
            updates["public_access"] = WorkflowAccessLevel.VIEW_ONLY
    elif pr.public_access == WorkflowAccessLevel.FIND_AND_VIEW:
        gui.write(
            WorkflowAccessLevel.FIND_AND_VIEW.get_public_sharing_text(pr=pr),
            unsafe_allow_html=True,
        )

    if can_user_edit:
        return updates
    else:
        return {}


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
        except WorkspaceMembership.DoesNotExist:
            return
        member_invite_button_with_dialog(
            membership,
            close_on_confirm=False,
            type="tertiary",
            className="mb-0",
        )


def render_share_options_for_personal_workspace(
    pr: PublishedRun,
) -> dict[str, WorkflowAccessLevel]:
    updates = {}
    options = {
        str(perm.value): perm.get_public_sharing_text(pr)
        for perm in WorkflowAccessLevel.get_public_sharing_options(pr)
    }

    with gui.div(className="mb-4"):
        updates["public_access"] = WorkflowAccessLevel(
            int(
                gui.radio(
                    "",
                    options=options,
                    format_func=options.__getitem__,
                    key="published-run-personal-permission",
                    value=str(pr.public_access),
                )
            )
        )
    return updates
