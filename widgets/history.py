from __future__ import annotations

import gooey_gui as gui
from furl import furl
from starlette.requests import Request

from app_users.models import AppUser
from bots.models import SavedRun
from daras_ai_v2 import icons
from daras_ai_v2.fastapi_tricks import get_route_path
from daras_ai_v2.meta_content import raw_build_meta_tags
from daras_ai_v2.urls import paginate_queryset
from gooey_gui.types.history_page_props import (
    HistoryPageProps,
    SurfaceTabData,
    WorkflowFilterOption,
)
from gooey_gui.types.home_page_props import WorkflowCardData
from routers.base_auth import get_login_url
from routers.custom_api_router import CustomAPIRouter
from routers.root import get_og_url_path, history_route, sidebar_page_wrapper
from widgets.surface_filters import (
    DEFAULT_SURFACE,
    SURFACE_ICONS,
    parse_surface,
    visible_surfaces,
)
from bots.models.workflow import Workflow, WorkflowMetadata
from widgets.workflow_cards import history_card, author_from_user
from workspaces.models import Workspace
from workspaces.widgets import get_current_workspace

META_TITLE = "History | Gooey.AI"
META_DESCRIPTION = "Your run history on Gooey.AI"

HISTORY_PAGE_SIZE = 24

app = CustomAPIRouter()


@gui.route(app, "/history/", "/history/{surface}/")
def history_page(request: Request, surface: str | None = None):
    history_surface = parse_surface(surface)
    with sidebar_page_wrapper(request):
        render(request, history_surface)

    return {
        "meta": build_meta_tags(url=get_og_url_path(request)),
    }


def render(request: Request, surface: SavedRun.Surface):
    user = request.user
    if user is None or user.is_anonymous:
        raise gui.RedirectException(get_login_url(request))

    surfaces = visible_surfaces(user)
    if surface not in surfaces:
        raise gui.RedirectException(_surface_href(DEFAULT_SURFACE))

    workspace = get_current_workspace(user, request.session)
    cards, load_more_href = _load_history(
        user=user,
        workspace=workspace,
        surface=surface,
        request=request,
    )

    gui.model_component(
        HistoryPageProps(
            workflow_options=_build_workflow_options(surface),
            surface_tabs=_build_surface_tabs(surface, surfaces),
            cards=cards,
            load_more_href=load_more_href,
            empty_message=f"No {surface.label} history yet.",
        )
    )


def build_meta_tags(url: str):
    return raw_build_meta_tags(
        url=url,
        title=META_TITLE,
        description=META_DESCRIPTION,
        robots="noindex,nofollow",
    )


def _load_history(
    *,
    user: AppUser,
    workspace: Workspace,
    surface: SavedRun.Surface,
    request: Request,
) -> tuple[list[WorkflowCardData], str | None]:
    # uses the ["workspace", "surface", "-updated_at"] index on SavedRun
    qs = SavedRun.objects.filter(workspace=workspace, surface=surface).select_related(
        "parent_version__published_run", "workflow_metadata", "created_by"
    )

    runs, next_cursor = paginate_queryset(
        qs=qs,
        ordering=["-updated_at"],
        cursor=request.query_params,
        page_size=HISTORY_PAGE_SIZE,
    )

    cards = [
        history_card(sr, author=author_from_user(sr.created_by, user)) for sr in runs
    ]
    return cards, _load_more_href(request, next_cursor)


def _build_workflow_options(surface: SavedRun.Surface) -> list[WorkflowFilterOption]:
    return [
        WorkflowFilterOption(
            id="",
            title=f"{icons.example}&nbsp; Any",
            href=_surface_href(surface),
            active=True,
        ),
    ] + [
        WorkflowFilterOption(
            id=str(metadata.workflow),
            title=f"{metadata.emoji} {metadata.short_title}",
            href=get_route_path(
                history_route,
                path_params={
                    "page_slug": Workflow(metadata.workflow).short_slug.lower()
                },
            ),
        )
        for metadata in WorkflowMetadata.objects.all().order_by("-priority")
    ]


def _build_surface_tabs(
    active: SavedRun.Surface, surfaces: list[SavedRun.Surface]
) -> list[SurfaceTabData]:
    return [
        SurfaceTabData(
            id=surface.name,
            title=surface.label,
            icon=SURFACE_ICONS.get(surface),
            href=_surface_href(surface),
            active=surface == active,
        )
        for surface in surfaces
    ]


def _surface_href(surface: SavedRun.Surface) -> str:
    return get_route_path(history_page, path_params={"surface": surface.name})


def _load_more_href(request: Request, next_cursor: dict[str, str] | None) -> str | None:
    if not next_cursor:
        return None
    f = furl(request.url).set(origin=None)
    f.query.params.update(next_cursor)
    return str(f)
