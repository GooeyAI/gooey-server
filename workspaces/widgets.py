import typing

import gooey_gui as gui

from app_users.models import AppUser
from daras_ai_v2 import icons
from daras_ai_v2.fastapi_tricks import get_route_path
from .models import Workspace

if typing.TYPE_CHECKING:
    from routers.account import AccountTabs


SESSION_SELECTED_WORKSPACE = "selected-workspace-id"


def workspace_selector(
    user: AppUser,
    session: dict,
    *,
    current_tab: "AccountTabs | None" = None,
):
    from routers.account import account_route, workspaces_route

    workspaces = user.get_workspaces().order_by("-is_personal", "-created_at")
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
        suffix = f" {len(workspaces) - 1}" if len(workspaces) > 1 else ""
        name = get_default_name_for_new_workspace(user, suffix=suffix)
        workspace = create_workspace_with_defaults(user, name=name)
        set_current_workspace(session, workspace.id)
        raise gui.RedirectException(
            get_workspaces_route_path(workspaces_route, workspace)
        )

    selected_id = gui.selectbox(
        label="",
        label_visibility="collapsed",
        options=choices.keys(),
        format_func=choices.get,
        key=SESSION_SELECTED_WORKSPACE,
        value=session.get(SESSION_SELECTED_WORKSPACE),
    )
    set_current_workspace(session, int(selected_id))
    if current_tab:
        workspace = next(w for w in workspaces if w.id == int(selected_id))
        if not validate_tab_for_workspace(current_tab, workspace):
            # account_route will redirect to the correct tab
            raise gui.RedirectException(get_route_path(account_route))


def get_current_workspace(user: AppUser, session: dict) -> Workspace:
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


def validate_tab_for_workspace(tab: "AccountTabs", workspace: Workspace) -> bool:
    from routers.account import AccountTabs

    if tab == AccountTabs.members:
        return not workspace.is_personal
    if tab == AccountTabs.profile:
        return workspace.is_personal
    return True


def get_workspaces_route_path(route_fn: typing.Callable, workspace: Workspace):
    """
    For routes like /workspaces/{workspace_slug}-{workspace_hashid}/...
    """
    if workspace.is_personal:
        return get_route_path(route_fn)
    else:
        return get_route_path(
            route_fn,
            path_params={
                "workspace_hashid": Workspace.api_hashids.encode(workspace.id),
                "workspace_slug": workspace.get_slug(),
            },
        )


def create_workspace_with_defaults(user: AppUser, name: str | None = None):
    if not name:
        workspace_count = user.get_workspaces().count()
        suffix = f" {workspace_count - 1}" if workspace_count > 1 else ""
        name = get_default_name_for_new_workspace(user, suffix=suffix)
    workspace = Workspace(name=name, created_by=user)
    workspace.create_with_owner()
    return workspace


def get_default_name_for_new_workspace(user: AppUser, suffix: str = "") -> str:
    return f"{user.first_name_possesive()} Team Workspace" + suffix
