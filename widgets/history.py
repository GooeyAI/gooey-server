from __future__ import annotations

from furl import furl
from starlette.requests import Request

import gooey_gui as gui
from app_users.models import AppUser
from bots.models import SavedRun
from bots.models.workflow import Workflow, WorkflowMetadata
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
from routers.root import get_og_url_path, sidebar_page_wrapper
from widgets.surface_filters import (
    DEFAULT_SURFACE,
    SURFACE_ICONS,
    parse_surface,
    surface_label,
    visible_surfaces,
)
from widgets.workflow_cards import author_from_user, history_card
from workspaces.models import Workspace
from workspaces.widgets import get_current_workspace

META_TITLE = "History | Gooey.AI"
META_DESCRIPTION = "Your run history on Gooey.AI"

HISTORY_PAGE_SIZE = 24

app = CustomAPIRouter()

OWNER_PARAM = "for"
OWNER_ALL = "all"
OWNER_ME = "me"


@gui.route(app, "/history/", "/history/{surface}/")
def history_page(request: Request, surface: str | None = None, workflow: str = ""):
    history_surface = parse_surface(surface)
    history_workflow = parse_workflow(workflow)
    with sidebar_page_wrapper(request):
        render(request, history_surface, history_workflow)

    return {
        "meta": build_meta_tags(url=get_og_url_path(request)),
    }


def render(
    request: Request,
    surface: SavedRun.Surface,
    workflow: Workflow | None,
):
    user = request.user
    if user is None or user.is_anonymous:
        raise gui.RedirectException(get_login_url(request))

    surfaces = visible_surfaces(user)
    if surface not in surfaces:
        raise gui.RedirectException(_surface_href(DEFAULT_SURFACE, workflow))

    workspace = get_current_workspace(user, request.session)
    mine_only = request.query_params.get(OWNER_PARAM, OWNER_ME) != OWNER_ALL
    cards, load_more_href = _load_history(
        user=user,
        workspace=workspace,
        surface=surface,
        workflow=workflow,
        mine_only=mine_only,
        request=request,
    )

    gui.model_component(
        HistoryPageProps(
            owner_options=_build_owner_options(
                user, workspace, surface, workflow, mine_only
            ),
            workflow_options=_build_workflow_options(surface, workflow, mine_only),
            surface_tabs=_build_surface_tabs(surface, surfaces, workflow, mine_only),
            cards=cards,
            load_more_href=load_more_href,
            empty_message=f"No {surface_label(surface).lower()} yet.",
        )
    )


def _build_owner_options(
    user: AppUser,
    workspace: Workspace,
    surface: SavedRun.Surface,
    workflow: Workflow | None,
    mine_only: bool,
) -> list[SurfaceTabData]:
    # a personal workspace holds nobody else's runs, so there is nothing to choose between
    if workspace.is_personal:
        return []
    return [
        SurfaceTabData(
            id=OWNER_ME,
            title="Just me",
            icon=(
                f'<img src="{user.get_photo()}" alt=""'
                f' style="width: 20px; height: 20px; border-radius: 50%;">'
            ),
            href=_surface_href(surface, workflow, mine_only=True),
            active=mine_only,
        ),
        SurfaceTabData(
            id=OWNER_ALL,
            title=workspace.display_name(user),
            icon=workspace.html_icon(size="20px"),
            href=_surface_href(surface, workflow, mine_only=False),
            active=not mine_only,
        ),
    ]


def parse_workflow(slug: str) -> Workflow | None:
    from daras_ai_v2.all_pages import normalize_slug, page_slug_map

    if not slug:
        return None
    page_cls = page_slug_map.get(normalize_slug(slug))
    return page_cls and page_cls.workflow


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
    workflow: Workflow | None,
    mine_only: bool,
    request: Request,
) -> tuple[list[WorkflowCardData], str | None]:
    # uses the ["workspace", "surface", "-updated_at"] index on SavedRun
    qs = SavedRun.objects.filter(workspace=workspace, surface=surface).select_related(
        "parent_version__published_run",
        "workflow_metadata",
        "created_by",
        "message_thread__bot_conversation",
    )
    if workflow is not None:
        qs = qs.filter(workflow=workflow)
    if mine_only:
        qs = qs.filter(uid=user.uid)

    runs, next_cursor = paginate_queryset(
        qs=qs,
        ordering=["-updated_at"],
        cursor=request.query_params,
        page_size=HISTORY_PAGE_SIZE,
    )

    cards = [
        history_card(sr, author=author_from_user(sr.created_by, user)) for sr in runs
    ]
    return cards, load_more_href(request, next_cursor)


def _build_workflow_options(
    surface: SavedRun.Surface,
    active_workflow: Workflow | None,
    mine_only: bool,
) -> list[WorkflowFilterOption]:
    options = [
        WorkflowFilterOption(
            id="",
            title=f"{icons.example}&nbsp; Any",
            href=_surface_href(surface, mine_only=mine_only),
            active=active_workflow is None,
        )
    ]
    workflows = _filterable_workflows(active_workflow)
    metadata_by_workflow = WorkflowMetadata.objects.in_bulk(
        workflows, field_name="workflow"
    )
    for workflow in workflows:
        metadata = metadata_by_workflow.get(workflow)
        if metadata is None:
            continue
        options.append(
            WorkflowFilterOption(
                id=workflow.page_cls.canonical_slug(),
                title=f"{metadata.emoji} {metadata.short_title}",
                href=_surface_href(surface, workflow, mine_only=mine_only),
                active=workflow == active_workflow,
            )
        )
    return options


def _filterable_workflows(active_workflow: Workflow | None) -> list[Workflow]:
    """The recipes still on offer, in /explore's order, plus whatever is filtered on now.

    Every workflow ever shipped has a `WorkflowMetadata` row, retired ones included.
    """
    from daras_ai_v2.all_pages import all_home_pages

    workflows = [page_cls.workflow for page_cls in all_home_pages]
    if active_workflow is not None and active_workflow not in workflows:
        workflows.append(active_workflow)
    return workflows


def _build_surface_tabs(
    active: SavedRun.Surface,
    surfaces: list[SavedRun.Surface],
    workflow: Workflow | None,
    mine_only: bool,
) -> list[SurfaceTabData]:
    return [
        SurfaceTabData(
            id=surface.name,
            title=surface_label(surface),
            icon=SURFACE_ICONS.get(surface),
            href=_surface_href(surface, workflow, mine_only=mine_only),
            active=surface == active,
        )
        for surface in surfaces
    ]


def history_href_for_workflow(workflow: Workflow) -> str:
    href = furl(get_route_path(history_page))
    href.args["workflow"] = workflow.page_cls.canonical_slug()
    return str(href)


def _surface_href(
    surface: SavedRun.Surface,
    workflow: Workflow | None = None,
    *,
    mine_only: bool = True,
) -> str:
    href = furl(get_route_path(history_page, path_params={"surface": surface.name}))
    if workflow is not None:
        href.args["workflow"] = workflow.page_cls.canonical_slug()
    if not mine_only:
        href.args[OWNER_PARAM] = OWNER_ALL
    return str(href)


def load_more_href(request: Request, next_cursor: dict[str, str] | None) -> str | None:
    if not next_cursor:
        return None
    f = furl(request.url).set(origin=None)
    f.query.params.update(next_cursor)
    return str(f)
