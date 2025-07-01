import typing
import html

import gooey_gui as gui
from furl import furl

from app_users.models import AppUser, obscure_phone_number
from daras_ai_v2 import icons, settings
from daras_ai_v2.fastapi_tricks import get_route_path
from handles.models import COMMON_EMAIL_DOMAINS
from .models import Workspace

if typing.TYPE_CHECKING:
    from payments.plans import PricingPlan


SESSION_SELECTED_WORKSPACE = "selected-workspace-id"
SWITCH_WORKSPACE_KEY = "--switch-workspace"


def global_workspace_selector(user: AppUser, session: dict):
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
        with gui.div(className="d-inline-flex align-items-center gap-2 text-truncate"):
            gui.html(f"{current.html_icon()}")
            gui.html(
                html.escape(display_name),
                className="d-none d-md-inline text-truncate",
                style={"maxWidth": "150px"},
            )
            gui.html('<i class="ps-1 fa-regular fa-chevron-down"></i>')

    with (
        content,
        gui.div(
            className="d-flex flex-column bg-white border border-dark rounded shadow mx-2 overflow-hidden",
        ),
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
            gui.html('<hr class="my-1"/>')
            with gui.tag(
                "button",
                className="bg-transparent border-0 text-start bg-hover-light px-3 my-1",
                name="--create-workspace",
                type="submit",
                value="yes",
                style=dict(height=row_height),
                onClick=open_create_workspace_popup_js(),
            ):
                with gui.div(className="row align-items-center"):
                    with gui.div(className="col-2 d-flex justify-content-center"):
                        gui.html(icons.octopus)
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
                        gui.html(icons.octopus)
                    with gui.div(className="col-10"):
                        if current.memberships.get(user=user).can_edit_workspace():
                            gui.html("Manage Workspace")
                        else:
                            gui.html("Open Workspace")

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
                        user.email
                        or str(
                            user.phone_number
                            and obscure_phone_number(user.phone_number)
                        ),
                        className="d-inline-block text-muted small ms-2",
                        style=dict(marginBottom="0.1rem"),
                    )

        with gui.div(className="d-xl-none d-inline-block"):
            for url, label in settings.HEADER_LINKS:
                with gui.tag(
                    "a",
                    href=url,
                    className="text-decoration-none d-block bg-hover-light align-items-center px-3 my-1 py-1",
                    style=dict(height=row_height),
                ):
                    col1, col2 = gui.columns(
                        [2, 10], responsive=False, className="row align-items-center"
                    )
                    if icon := settings.HEADER_ICONS.get(url):
                        with (
                            col1,
                            gui.div(className="d-flex justify-content-center"),
                        ):
                            gui.html(icon)
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


def render_create_workspace_alert():
    with gui.div(className="alert alert-warning my-0 container-margin-reset"):
        gui.button(
            f"{icons.company} Create a team workspace",
            type="link",
            className="d-inline mb-1 me-1 p-0",
            onClick=open_create_workspace_popup_js(),
        )
        gui.html("to edit with others", className="d-inline")


def open_create_workspace_popup_js(
    selected_plan: typing.Optional["PricingPlan"] = None,
):
    from routers.workspace import create_workspace_route
    from routers.account import account_route

    next_url = get_route_path(account_route)
    popup_url = furl(
        get_route_path(create_workspace_route), query_params={"next": next_url}
    )
    if selected_plan:
        popup_url.query.params["selected_plan"] = selected_plan.db_value
        next_url = ""  # don't redirect as we are already on the account page

    # language=javascript
    return """
        let popupUrl = %r;
        let nextUrl = %r;
        
        window.addEventListener("message", function(event) {
            if (!event.data.workspaceCreated) return;
            if (nextUrl) { 
                gui.navigate(nextUrl);
            } else {
                gui.rerun()
            } 
        });
        
        // try to open the popup
        let popup = window.open(popupUrl, "create_workspace", "width=1000,height=600,scrollbars=yes,resizable=yes");
        // if the popup was blocked, open it in a new tab
        if (!popup) {
           popup = window.open(popupUrl, "_blank");
        }
        // if the popup was blocked, redirect to the url
        if (!popup)  {
            event.preventDefault();
            gui.navigate(popupUrl);
        }
        """ % (
        str(popup_url),
        next_url,
    )


def get_workspace_domain_name_options(
    workspace: Workspace, current_user: AppUser
) -> set | None:
    current_user_domain = (
        current_user.email and current_user.email.lower().rsplit("@", maxsplit=1)[-1]
    )
    options = {workspace.domain_name, None}
    if current_user_domain not in COMMON_EMAIL_DOMAINS:
        options.add(current_user_domain)
    return len(options) > 1 and options or None
