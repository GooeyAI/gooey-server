from __future__ import annotations

from starlette.requests import Request

from daras_ai_v2 import settings
from daras_ai_v2.fastapi_tricks import get_route_path
from gooey_gui.types.home_page_props import (
    ChatPreview,
    IconPreview,
    MediaPreview,
    WorkflowCardData,
)
from gooey_gui.types.navigation_sidebar_props import (
    MenuLinkData,
    NavItemData,
    NavUserData,
    NavWorkflowData,
    NavigationSidebarProps,
    WorkspaceData,
)


def _card_to_nav_workflow(card: WorkflowCardData) -> NavWorkflowData:
    image_url: str | None = None
    preview = card.preview
    if isinstance(preview, MediaPreview):
        image_url = preview.preview_img or preview.url
    elif isinstance(preview, IconPreview):
        image_url = preview.image_url
    # ChatPreview → no image

    return NavWorkflowData(
        title=card.title,
        href=card.href,
        icon=card.workflow_icon,
        image_url=image_url,
    )


def build_props(request: Request, default_collapsed: bool = False) -> NavigationSidebarProps:
    from routers.root import explore_page, home_page
    from routers.account import account_route, members_route, profile_route, saved_route
    from routers.base_auth import logout
    from routers.workspace import switch_workspace_route
    from widgets.home import _load_recent_workflows, _load_saved_workflows, _saved_workflows_href
    from workspaces.widgets import get_current_workspace

    home_path = get_route_path(home_page)
    explore_path = get_route_path(explore_page)
    saved_path = get_route_path(saved_route)

    current_path = request.url.path

    if current_path == home_path or current_path.rstrip("/") == home_path.rstrip("/"):
        active_key: str | None = "home"
    elif current_path == explore_path or current_path.rstrip("/") == explore_path.rstrip("/"):
        active_key = "explore"
    elif current_path == saved_path or current_path.rstrip("/") == saved_path.rstrip("/"):
        active_key = "saved"
    else:
        active_key = None

    is_anonymous = request.user is None or request.user.is_anonymous
    if is_anonymous:
        user = None
        workspace = None
    else:
        user = request.user
        workspace = get_current_workspace(user, request.session)

    recent_cards = _load_recent_workflows(user, workspace)[:10]
    saved_cards = _load_saved_workflows(user, workspace)

    nav_user: NavUserData | None = None
    current_workspace_data: WorkspaceData | None = None
    workspaces_data: list[WorkspaceData] = []
    menu_links: list[MenuLinkData] = []
    logout_href = ""
    switch_workspace_href = ""

    if not is_anonymous:
        nav_user = NavUserData(
            name=user.display_name or user.first_name(),
            initial=(user.first_name() or "?")[:1].upper(),
            photo_url=user.photo_url or None,
        )

        for ws in user.cached_workspaces:
            ws_data = WorkspaceData(
                id=ws.id,
                name=ws.display_name(user),
                icon_html=ws.html_icon(),
                is_current=workspace is not None and ws.id == workspace.id,
            )
            workspaces_data.append(ws_data)
            if ws_data.is_current:
                current_workspace_data = ws_data

        menu_links = [
            MenuLinkData(
                label="Profile",
                href=get_route_path(profile_route),
                icon="fa-regular fa-address-card",
            ),
            MenuLinkData(
                label="Billing",
                href=get_route_path(account_route),
                icon="fa-regular fa-square-dollar",
            ),
            MenuLinkData(
                label="Members",
                href=get_route_path(members_route),
                icon="fa-regular fa-users",
            ),
        ]
        for url, label in settings.HEADER_LINKS:
            if label == "Explore":
                continue  # already a primary nav item
            menu_links.append(
                MenuLinkData(label=label, href=url, icon=settings.HEADER_ICONS.get(url))
            )

        logout_href = get_route_path(logout)

        # Path template; React substitutes the real id per workspace row.
        switch_workspace_href = get_route_path(
            switch_workspace_route, path_params={"workspace_id": 0}
        ).replace("/0/", "/{workspace_id}/")

    return NavigationSidebarProps(
        logo_image_url=settings.GOOEY_LOGO_IMG,
        nav_items=[
            NavItemData(
                key="home",
                label="Home",
                icon="fa-regular fa-house",
                href=home_path,
            ),
            NavItemData(
                key="explore",
                label="Explore",
                icon="fa-regular fa-magnifying-glass",
                href=explore_path,
            ),
            NavItemData(
                key="saved",
                label="Saved",
                icon="fa-regular fa-floppy-disk",
                href=saved_path,
            ),
        ],
        active_key=active_key,
        new_href="/explore2/",
        default_collapsed=default_collapsed,
        saved_href=_saved_workflows_href(workspace),
        saved_workflows=[_card_to_nav_workflow(c) for c in saved_cards],
        recent_workflows=[_card_to_nav_workflow(c) for c in recent_cards],
        user=nav_user,
        current_workspace=current_workspace_data,
        workspaces=workspaces_data,
        menu_links=menu_links,
        logout_href=logout_href,
        switch_workspace_href=switch_workspace_href,
    )
