import typing

import gooey_gui as gui

from app_users.models import AppUser
from daras_ai_v2 import icons
from daras_ai_v2.fastapi_tricks import get_route_path
from .models import Workspace

SESSION_SELECTED_WORKSPACE = "selected-workspace-id"


def workspace_selector(
    user: AppUser,
    session: dict,
    *,
    route_fn: typing.Callable | None = None,
):
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
    if route_fn:
        workspace = next(w for w in workspaces if w.id == int(selected_id))
        next_route_fn = get_next_route_fn(route_fn, workspace)
        if route_fn != next_route_fn:
            # redirect is needed
            raise gui.RedirectException(
                get_workspaces_route_path(next_route_fn, workspace)
            )


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


def get_next_route_fn(
    route_fn: typing.Callable, workspace: Workspace
) -> typing.Callable:
    """
    When we need to redirect after user changes the workspace.
    """
    from routers.account import (
        account_route,
        profile_route,
        workspaces_route,
        workspaces_members_route,
    )

    if workspace.is_personal and route_fn in (
        workspaces_members_route,
        workspaces_route,
    ):
        # personal workspaces don't have a members page
        # account_route does the right redirect instead
        return account_route
    elif not workspace.is_personal and route_fn == profile_route:
        # team workspaces don't have a profile page
        # workspaces_route does the right redirect instead
        return workspaces_route

    return route_fn


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
