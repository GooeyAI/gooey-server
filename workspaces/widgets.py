import gooey_gui as gui

from app_users.models import AppUser
from daras_ai_v2 import icons, settings
from daras_ai_v2.fastapi_tricks import get_route_path
from handles.models import COMMON_EMAIL_DOMAINS
from .models import Workspace


SESSION_SELECTED_WORKSPACE = "selected-workspace-id"
SWITCH_WORKSPACE_KEY = "--switch-workspace"


def global_workspace_selector(user: AppUser, session: dict):
    from daras_ai_v2.base import BasePage
    from routers.account import members_route, profile_route

    try:
        del user.cached_workspaces  # invalidate cache on every re-render
    except AttributeError:
        pass
    workspaces = user.cached_workspaces

    if switch_workspace_id := gui.session_state.pop(SWITCH_WORKSPACE_KEY, None):
        try:
            if str(session[SESSION_SELECTED_WORKSPACE]) == switch_workspace_id:
                raise gui.RedirectException(get_route_path(members_route))
        except KeyError:
            pass
        set_current_workspace(session, int(switch_workspace_id))

    try:
        current = [
            w for w in workspaces if w.id == session[SESSION_SELECTED_WORKSPACE]
        ][0]
    except (KeyError, IndexError):
        current = workspaces[0]

    popover, content = gui.popover(interactive=True, placement="bottom")

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
                    current.html_icon(),
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
                name=SWITCH_WORKSPACE_KEY,
                type="submit",
                value=str(workspace.id),
                style=dict(height=row_height),
            ):
                with gui.div(className="row align-items-center"):
                    with gui.div(className="col-2 d-flex justify-content-center"):
                        gui.html(workspace.html_icon())
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
                to=get_route_path(members_route),
                className="text-decoration-none d-block bg-hover-light px-3 my-1 py-1",
                style=dict(height=row_height),
            ):
                with gui.div(className="row align-items-center"):
                    with gui.div(className="col-2 d-flex justify-content-center"):
                        gui.html('<i class="fa-regular fa-octopus"></i>')
                    with gui.div(className="col-10"):
                        if current.memberships.get(user=user).can_edit_workspace():
                            gui.html("Manage Workspace")
                        else:
                            gui.html("Open Workspace")

        if gui.session_state.pop("--create-workspace", None):
            name = get_default_workspace_name_for_user(user)
            workspace = Workspace(name=name, created_by=user)
            workspace.create_with_owner()
            session[SESSION_SELECTED_WORKSPACE] = workspace.id
            raise gui.RedirectException(get_route_path(members_route))

        gui.html('<hr class="my-1"/>')

        with gui.link(
            to=get_route_path(profile_route),
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
                        str(user.email or user.phone_number),
                        className="d-inline-block text-muted small ms-2",
                        style=dict(marginBottom="0.1rem"),
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

    return current


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


def get_default_workspace_name_for_user(user: AppUser) -> str:
    workspace_count = len(user.cached_workspaces)
    email_domain = user.email and user.email.split("@", maxsplit=1)[1] or ""
    if (
        email_domain
        and email_domain not in COMMON_EMAIL_DOMAINS
        and workspace_count <= 1
    ):
        email_domain_prefix = email_domain.split(".")[0].title()
        return f"{email_domain_prefix} Team"

    suffix = f" {workspace_count - 1}" if workspace_count > 1 else ""
    return f"{user.first_name_possesive()} Team Workspace" + suffix
