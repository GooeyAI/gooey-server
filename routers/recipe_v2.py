"""Routes for the layout-v2 tab urls.

Every v2 tab slug gets one thin route with the same three path variants v1 uses:

    /video-bots/config/
    /video-bots/my-agent/config/
    /video-bots/my-agent-abc123/config/

Slugs that v1 already routes (`""` -> `/{page_slug}/`, `"preview"` ->
`/{page_slug}/preview/`, ...) are skipped: those urls are shared with v1 and the fork switch
in `render_recipe_page` already dispatches them to the v2 page class.

A bare `/{page_slug}/{tab_slug}/` catch-all is deliberately avoided - a published run titled
"Config" would collide with it and become unreachable.
"""

import re
import typing
from functools import cache

import gooey_gui as gui
from starlette.requests import Request
from starlette.responses import Response

from daras_ai_v2.all_pages import normalize_slug
from daras_ai_v2.all_pages_v2 import page_slug_map_v2
from daras_ai_v2.fastapi_tricks import get_route_path
from routers import root
from routers.custom_api_router import CustomAPIRouter
from routers.root import RecipePageNotFound, RecipeTabs, render_recipe_page

app = CustomAPIRouter()

# `/{page_slug}/api/` -> "api", `/{page_slug}/` -> ""
_V1_TAB_PATH_RE = re.compile(r"^/\{page_slug\}/(?P<slug>[^/{}]*)/?$")


@cache
def v1_tab_slugs() -> dict[RecipeTabs, str]:
    """Url slug of each v1 tab, read off the routes registered in `routers.root` so it can
    never drift from them. `RecipeTabs.run` maps to "" - it is the entry url.
    """
    slug_by_route_name = {}
    for route in root.app.routes:
        match = _V1_TAB_PATH_RE.match(getattr(route, "path", ""))
        if match:
            slug_by_route_name.setdefault(route.name, match.group("slug"))
    return {
        tab: slug
        for tab in RecipeTabs
        if (slug := slug_by_route_name.get(tab.route.__name__)) is not None
    }


@cache
def _v1_tab_by_slug() -> dict[str, RecipeTabs]:
    return {slug: tab for tab, slug in v1_tab_slugs().items()}


def render_recipe_page_v2(
    request: Request, page_slug: str, example_id: str | None
) -> dict | Response:
    """A v2 tab url only exists for a recipe that has a v2 fork, and only for users the gate
    lets through. Everyone else gets the 404 the url gave before it was registered.
    """
    from daras_ai_v2.layout_v2 import can_use_layout_v2

    # can_use_layout_v2() reads settings.ENABLE_LAYOUT_V2 first, so a closed kill switch
    # costs one settings read
    if not can_use_layout_v2(request):
        raise RecipePageNotFound
    if normalize_slug(page_slug) not in page_slug_map_v2:
        raise RecipePageNotFound

    # the active tab is resolved from the url by BasePage.render(), which has to do that
    # anyway for the urls v1 owns (the entry url and /preview/)
    return render_recipe_page(request, page_slug, RecipeTabs.run, example_id)


def _register_tab_route(slug: str) -> typing.Callable:
    def tab_route(
        request: Request,
        page_slug: str,
        run_slug: str = None,
        example_id: str = None,
    ):
        return render_recipe_page_v2(request, page_slug, example_id)

    # get_route_path() resolves a route by function name, so each slug needs its own
    tab_route.__name__ = f"recipe_v2_{slug.replace('-', '_')}_route"

    return gui.route(
        app,
        f"/{{page_slug}}/{slug}/",
        f"/{{page_slug}}/{{run_slug}}/{slug}/",
        f"/{{page_slug}}/{{run_slug}}-{{example_id}}/{slug}/",
    )(tab_route)


def _register_all_tab_routes() -> dict[str, typing.Callable]:
    slugs = {
        slug
        for page_cls in page_slug_map_v2.values()
        for slug in page_cls.all_tab_slugs()
    }
    v1_owned = set(_v1_tab_by_slug())
    return {slug: _register_tab_route(slug) for slug in sorted(slugs - v1_owned)}


def tab_url_path(
    slug: str,
    *,
    page_slug: str,
    run_slug: str | None = None,
    example_id: str | None = None,
    **path_params,
) -> str:
    """Path of a v2 tab url, mirroring `RecipeTabs.url_path()`."""
    tab = _v1_tab_by_slug().get(slug)
    if tab is not None:
        # shared url, owned by v1
        return tab.url_path(
            page_slug=page_slug,
            run_slug=run_slug,
            example_id=example_id,
            **path_params,
        )

    try:
        route = tab_routes[slug]
    except KeyError:
        raise KeyError(
            f"no v2 tab route for slug {slug!r} - "
            f"every TabSpec slug must also be returned by all_tab_slugs()"
        ) from None

    path_params["page_slug"] = page_slug
    if example_id:
        path_params["example_id"] = example_id
        path_params["run_slug"] = run_slug or "untitled"
    return get_route_path(route, path_params)


tab_routes: dict[str, typing.Callable] = _register_all_tab_routes()
