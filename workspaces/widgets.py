import gooey_gui as gui

from app_users.models import AppUser
from daras_ai_v2 import icons, settings
from daras_ai_v2.fastapi_tricks import get_route_path
from .models import Workspace

SESSION_SELECTED_WORKSPACE = "selected-workspace-id"


def workspace_selector(user: AppUser, session: dict, key: str = "global-selector"):
    from daras_ai_v2.base import BasePage
    from routers.account import workspaces_route

    workspaces = Workspace.objects.filter(
        memberships__user=user, memberships__deleted__isnull=True
    ).order_by("-is_personal", "-created_at")
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
        className="d-flex flex-column bg-white border border-dark rounded shadow"
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
                to="/workspaces/",
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
                with gui.div(className="col-10 d-flex justify-content-between"):
                    with gui.div(className="pe-3"):
                        gui.html("Profile")
                    with gui.div(className="text-muted small"):
                        gui.html(user.email or user.phone_number)

        with gui.div(className="d-lg-none d-inline-block"):
            for url, label in settings.HEADER_LINKS:
                with gui.link(
                    to=url,
                    className="text-decoration-none d-block bg-hover-light align-items-center px-3 my-1 py-1",
                    style=dict(height=row_height),
                ):
                    col1, col2 = gui.columns([2, 10], responsive=False)
                    with col2:
                        gui.html(label)

        with gui.link(
            to="/logout/",
            className="text-decoration-none d-block bg-hover-light align-items-center px-3 my-1 py-1",
            style=dict(height=row_height),
        ):
            with gui.div(className="row align-items-center"):
                with gui.div(className="col-2 d-flex justify-content-center"):
                    gui.html(icons.sign_out)
                with gui.div(className="col-10"):
                    gui.html("Log out")


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
