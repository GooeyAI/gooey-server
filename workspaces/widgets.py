import typing

import gooey_gui as gui
from furl import furl

from app_users.models import AppUser
from daras_ai_v2 import icons
from daras_ai_v2.fastapi_tricks import get_route_path
from handles.models import COMMON_EMAIL_DOMAINS
from .models import Workspace

if typing.TYPE_CHECKING:
    from daras_ai_v2.billing import SeatSelection
    from payments.plans import PricingPlan


SESSION_SELECTED_WORKSPACE = "selected-workspace-id"
SWITCH_WORKSPACE_KEY = "--switch-workspace"


def handle_workspace_switch(session: dict):
    switch_workspace_id = gui.session_state.pop(SWITCH_WORKSPACE_KEY, None)
    if not switch_workspace_id:
        return

    from routers.account import members_route

    try:
        if str(session[SESSION_SELECTED_WORKSPACE]) == switch_workspace_id:
            raise gui.RedirectException(get_route_path(members_route))
    except KeyError:
        pass
    set_current_workspace(session, int(switch_workspace_id))


def get_current_workspace(user: AppUser, session: dict) -> Workspace:
    try:
        workspace = next(
            w
            for w in user.cached_workspaces
            if w.id == session[SESSION_SELECTED_WORKSPACE]
        )
    except (KeyError, StopIteration):
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
    seat_selection: typing.Optional["SeatSelection"] = None,
):
    popup_url, next_url = get_create_workspace_popup_url(
        selected_plan=selected_plan, seat_selection=seat_selection
    )

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

        // try to open in new tab
        popup = window.open(popupUrl, "_blank");
        // if the popup was blocked in new tab, redirect to the url
        if (!popup)  {
            event.preventDefault();
            gui.navigate(popupUrl);
        }
        """ % (
        popup_url,
        next_url,
    )


def get_create_workspace_popup_url(
    selected_plan: typing.Optional["PricingPlan"] = None,
    seat_selection: typing.Optional["SeatSelection"] = None,
) -> tuple[str, str]:
    """Build ``(popup_url, next_url)`` for the create-workspace flow.

    ``popup_url`` opens the workspace-creation popup; ``next_url`` is where the
    opener should navigate once the popup posts ``workspaceCreated`` (empty
    string => rerun in place). Shared by the server-rendered onClick
    (``open_create_workspace_popup_js``) and the React navigation sidebar so both
    follow the exact same logic.
    """
    from routers.workspace import create_workspace_route
    from routers.account import account_route

    next_url = get_route_path(account_route)
    popup_url = furl(
        get_route_path(create_workspace_route), query_params={"next": next_url}
    )
    if selected_plan:
        popup_url.query.params["selected_plan"] = selected_plan.db_value
        if seat_selection:
            popup_url.query.params["selected_seat_type"] = seat_selection[0].key
            popup_url.query.params["selected_seat_count"] = str(seat_selection[1])
        next_url = ""  # don't redirect as we are already on the account page

    return str(popup_url), next_url


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
