from __future__ import annotations

from starlette.requests import Request

from daras_ai_v2 import settings
from daras_ai_v2.fastapi_tricks import get_route_path
from gooey_gui.types.navigation_sidebar_props import (
    NavItemData,
    NavigationSidebarProps,
)


def build_props(request: Request) -> NavigationSidebarProps:
    from routers.root import explore_page, home_page
    from routers.account import saved_route

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
    )
