import gooey_gui as gui

from app_users.models import AppUser
from daras_ai_v2 import icons
from daras_ai_v2.fastapi_tricks import get_route_path
from .models import Workspace

SESSION_SELECTED_WORKSPACE = "selected-workspace-id"


def workspace_selector(user: AppUser, session: dict):
    from routers.account import workspaces_route

    workspaces = Workspace.objects.filter(
        memberships__user=user, memberships__deleted__isnull=True
    ).order_by("-is_personal", "-created_at")
    if not workspaces:
        workspaces = [user.get_or_create_personal_workspace()[0]]

    choices = {
        workspace.id: "&nbsp;&nbsp;".join(
            [workspace.html_icon(user), workspace.display_name(user)]
        )
        for workspace in workspaces
    } | {
        "<create>": f"{icons.add} Create Workspace",
    }

    if gui.session_state.get(SESSION_SELECTED_WORKSPACE) == "<create>":
        name = f"{user.first_name_possesive()} Team Workspace"
        if len(workspaces) > 1:
            name += f" {len(workspaces) - 1}"
        workspace = Workspace(name=name, created_by=user)
        workspace.create_with_owner()
        gui.session_state[SESSION_SELECTED_WORKSPACE] = workspace.id
        session[SESSION_SELECTED_WORKSPACE] = workspace.id
        raise gui.RedirectException(get_route_path(workspaces_route))

    selected_id = gui.selectbox(
        label="",
        label_visibility="collapsed",
        options=choices.keys(),
        format_func=choices.get,
        key=SESSION_SELECTED_WORKSPACE,
        value=session.get(SESSION_SELECTED_WORKSPACE),
    )
    set_current_workspace(session, int(selected_id))


def get_current_workspace(user: AppUser, session: dict) -> "Workspace":
    try:
        workspace_id = session[SESSION_SELECTED_WORKSPACE]
        return Workspace.objects.get(
            id=workspace_id,
            memberships__user=user,
            memberships__deleted__isnull=True,
        )
    except (KeyError, Workspace.DoesNotExist):
        workspace = user.get_or_create_personal_workspace()[0]
        set_current_workspace(session, workspace.id)
        return workspace


def set_current_workspace(session: dict, workspace_id: int):
    session[SESSION_SELECTED_WORKSPACE] = workspace_id
