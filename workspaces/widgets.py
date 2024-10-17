import typing

import gooey_gui as gui

from app_users.models import AppUser
from daras_ai_v2 import icons, settings
from daras_ai_v2.fastapi_tricks import get_route_path
from .models import Workspace

if typing.TYPE_CHECKING:
    from routers.account import AccountTabs


SESSION_SELECTED_WORKSPACE = "selected-workspace-id"


def workspace_selector(
    user: AppUser,
    session: dict,
    *,
    key: str = "global-selector",
    current_tab: "AccountTabs | None" = None,
):
    from daras_ai_v2.base import BasePage
    from routers.account import account_route, workspaces_route

    workspaces = user.get_workspaces().order_by("-is_personal", "-created_at")
    if not workspaces:
        workspaces = [user.get_or_create_personal_workspace()[0]]

    if str(gui.session_state.get(key)).startswith("__url:"):
        raise gui.RedirectException(gui.session_state[key].removeprefix("__url:"))

    if switch_workspace_id := gui.session_state.pop("--switch-workspace", None):
        set_current_workspace(session, int(switch_workspace_id))

    try:
        current = [
            w for w in workspaces if w.id == session[SESSION_SELECTED_WORKSPACE]
        ][0]
    except (KeyError, IndexError):
        current = workspaces[0]

    if current_tab and not validate_tab_for_workspace(current_tab, current):
        # account_route will redirect to the correct tab
        raise gui.RedirectException(get_route_path(account_route))

    popover, content = gui.popover(interactive=True)

    with popover:
        if current.is_personal and current.created_by_id == user.id:
            if len(workspaces) == 1:
                display_name = user.first_name()
            else:
                display_name = "Personal"
        else:
            display_name = current.display_name(user)
        gui.html(
            " ".join(
                [
                    current.html_icon(user),
                    display_name,
                    '<i class="ps-1 fa-regular fa-chevron-down"></i>',
                ],
            ),
        )

    with content, gui.div(
        className="d-flex flex-column bg-white border border-dark rounded shadow mx-2 overflow-hidden",
    ):
        row_height = "2.2rem"

        for workspace in workspaces:
            with gui.tag(
                "button",
                className="bg-transparent border-0 text-start bg-hover-light px-3 my-1",
                name="--switch-workspace",
                type="submit",
                value=str(workspace.id),
                style=dict(height=row_height),
            ):
                with gui.div(className="row align-items-center"):
                    with gui.div(className="col-2 d-flex justify-content-center"):
                        gui.html(workspace.html_icon(user))
                    with gui.div(
                        className="col-10 d-flex justify-content-between align-items-center"
                    ):
                        with gui.div(className="pe-3"):
                            gui.html(workspace.display_name(user))
                        if workspace.id == current.id:
                            gui.html(
                                '<i class="fa-sharp fa-solid fa-circle-check"></i>'
                            )

        if current.is_personal:
            if BasePage.is_user_admin(user):
                gui.html('<hr class="my-1"/>')
                with gui.tag(
                    "button",
                    className="bg-transparent border-0 text-start bg-hover-light px-3 my-1",
                    name="--create-workspace",
                    type="submit",
                    value="yes",
                    style=dict(height=row_height),
                ):
                    with gui.div(className="row align-items-center"):
                        with gui.div(className="col-2 d-flex justify-content-center"):
                            gui.html('<i class="fa-regular fa-octopus"></i>')
                        with gui.div(className="col-10"):
                            gui.html("New Team Workspace")
        else:
            gui.html('<hr class="my-1"/>')
            with gui.link(
                to=get_route_path_for_workspace(workspaces_route, workspace=current),
                className="text-decoration-none d-block bg-hover-light px-3 my-1 py-1",
                style=dict(height=row_height),
            ):
                with gui.div(className="row align-items-center"):
                    with gui.div(className="col-2 d-flex justify-content-center"):
                        gui.html('<i class="fa-regular fa-octopus"></i>')
                    with gui.div(className="col-10"):
                        gui.html("Manage Workspace")

        if gui.session_state.pop("--create-workspace", None):
            name = f"{user.first_name_possesive()} Team Workspace"
            if len(workspaces) > 1:
                name += f" {len(workspaces) - 1}"
            workspace = Workspace(name=name, created_by=user)
            workspace.create_with_owner()
            gui.session_state[key] = workspace.id
            session[SESSION_SELECTED_WORKSPACE] = workspace.id
            raise gui.RedirectException(get_route_path(workspaces_route))

        gui.html('<hr class="my-1"/>')

        with gui.link(
            to="/account/profile/",
            className="text-decoration-none d-block bg-hover-light align-items-center px-3 my-1 py-1",
            style=dict(height=row_height),
        ):
            with gui.div(className="row align-items-center"):
                with gui.div(className="col-2 d-flex justify-content-center"):
                    gui.html(icons.profile)
                with gui.div(
                    className="col-10 d-flex justify-content-between align-items-end"
                ):
                    gui.html(
                        "Profile",
                        className="d-inline-block",
                    )
                    gui.html(
                        user.email or user.phone_number,
                        className="d-inline-block text-muted small",
                    )

        with gui.div(className="d-lg-none d-inline-block"):
            for url, label in settings.HEADER_LINKS:
                with gui.tag(
                    "a",
                    href=url,
                    className="text-decoration-none d-block bg-hover-light align-items-center px-3 my-1 py-1",
                    style=dict(height=row_height),
                ):
                    col1, col2 = gui.columns([2, 10], responsive=False)
                    with col2:
                        gui.html(label)

        with gui.tag(
            "a",
            href="/logout/",
            className="text-decoration-none d-block bg-hover-light align-items-center px-3 my-1 py-1",
            style=dict(height=row_height),
        ):
            with gui.div(className="row align-items-center"):
                with gui.div(className="col-2 d-flex justify-content-center"):
                    gui.html(icons.sign_out)
                with gui.div(className="col-10"):
                    gui.html("Log out")


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


def get_route_path_for_workspace(route_fn: typing.Callable, workspace: Workspace):
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
