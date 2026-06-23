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
    NavItemData,
    NavWorkflowData,
    NavigationSidebarProps,
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
    from routers.account import saved_route
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
    )
