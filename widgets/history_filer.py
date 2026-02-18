from __future__ import annotations

import gooey_gui as gui
from typing import TYPE_CHECKING
from furl import furl

if TYPE_CHECKING:
    from daras_ai_v2.base import BasePageRequest
    from workspaces.models import Workspace


def render_history_filter_desktop(
    request: BasePageRequest,
    current_workspace: Workspace,
    current_app_url: str,
) -> None:
    """Desktop history filter - absolute positioned on the right (lg+ only)"""
    with gui.div(
        className="container-margin-reset d-none d-lg-block",
        style={
            "position": "absolute",
            "top": "50%",
            "right": "0",
            "transform": "translateY(-50%)",
            "fontSize": "smaller",
            "fontWeight": "normal",
        },
    ):
        render_history_filter_content(request, current_workspace, current_app_url)


def render_history_filter_mobile(
    request: BasePageRequest,
    current_workspace: Workspace,
    current_app_url: str,
) -> None:
    """Mobile history filter - below nav tabs (lg and below)"""
    with gui.div(
        className="d-block d-lg-none mt-2",
        style={
            "fontSize": "smaller",
            "fontWeight": "normal",
        },
    ):
        render_history_filter_content(request, current_workspace, current_app_url)


def render_history_filter_content(
    request: BasePageRequest,
    current_workspace: Workspace,
    current_app_url: str,
) -> bool | None:
    """Common logic for rendering history filter - returns filter data or None if not applicable"""
    if not request.user or request.user.is_anonymous or current_workspace.is_personal:
        return None

    # Get current filter parameter
    for_param = request.query_params.get("for", "me")
    show_all_history = for_param == "all"

    # Get icons
    user_photo = request.user.get_photo()
    user_icon = f'<img src="{user_photo}" style="width: 20px; height: 20px; border-radius: 50%;" />'
    workspace_icon = current_workspace.html_icon(size="20px")

    # Render the filter buttons
    with (
        gui.styled("""
          & .btn-outline-dark:hover { color: white !important; }
        """),
        gui.div(className="btn-group", role="group"),
    ):
        btn_class = "btn btn-sm btn-outline-secondary d-flex align-items-center gap-1"

        # "Just mine" link
        for_me_furl = furl(current_app_url)
        for_me_furl.args["for"] = "me"
        for_me_url = for_me_furl.url
        if not show_all_history:
            for_me_cls = " active"
        else:
            for_me_cls = ""
        with gui.link(
            to=for_me_url,
            className=btn_class + for_me_cls,
        ):
            gui.html(user_icon)
            gui.html("Just mine")

        # "All {workspace}" link
        for_all_furl = furl(current_app_url)
        for_all_furl.args["for"] = "all"
        for_all_url = for_all_furl.url
        if show_all_history:
            show_all_history_cls = " active"
        else:
            show_all_history_cls = ""
        with gui.link(
            to=for_all_url,
            className=btn_class + show_all_history_cls,
        ):
            gui.html("All")
            gui.html(workspace_icon)

    return show_all_history
