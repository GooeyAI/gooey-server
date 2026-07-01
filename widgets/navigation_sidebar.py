from __future__ import annotations

from typing import TYPE_CHECKING

import gooey_gui as gui
from starlette.requests import Request

from daras_ai_v2 import settings
from daras_ai_v2.base import BasePage
from daras_ai_v2.fastapi_tricks import get_route_path
from gooey_gui.types.navigation_sidebar_props import (
    GooeyBuilderData,
    MenuLinkData,
    NavAccountData,
    NavItemData,
    NavUserData,
    NavWorkflowItem,
    NavigationSidebarProps,
    WorkspaceData,
)

if TYPE_CHECKING:
    from app_users.models import AppUser
    from bots.models import PublishedRun, SavedRun
    from bots.models.workflow import WorkflowMetadata
    from workspaces.models import Workspace

RECENT_WORKFLOW_LIST_LIMIT = 20


def render(
    request: Request,
    default_collapsed: bool = False,
    page: BasePage | None = None,
) -> None:
    from routers.base_auth import get_login_url, logout
    from routers.root import explore_page, home_page
    from widgets.home import _saved_workflows_href
    from workspaces.widgets import (
        get_create_workspace_popup_url,
        get_current_workspace,
        handle_workspace_switch,
    )

    home_path = get_route_path(home_page)
    explore_path = get_route_path(explore_page)

    is_anonymous = request.user is None or request.user.is_anonymous
    if is_anonymous:
        user = None
        workspace = None
    else:
        user = request.user
        handle_workspace_switch(request.session)
        workspace = get_current_workspace(user, request.session)

    saved_path = _saved_workflows_href(workspace)
    workspaces = _load_workspaces(user, workspace)

    active_key = _active_nav_key(
        request.url.path,
        {"home": home_path, "explore": explore_path, "saved": saved_path},
    )

    if is_anonymous:
        add_workspace_url = ""
    else:
        add_workspace_url, _ = get_create_workspace_popup_url()

    gui.model_component(
        NavigationSidebarProps(
            logo_image_url=settings.GOOEY_LOGO_IMG,
            nav_items=_load_nav_items(
                is_anonymous,
                home_path=home_path,
                explore_path=explore_path,
                saved_path=saved_path,
                saved_workflows=_load_saved_workflows(user, workspace),
            ),
            active_key=active_key,
            default_collapsed=default_collapsed,
            recent_workflows=_load_recent_workflows(
                user, workspace, limit=RECENT_WORKFLOW_LIST_LIMIT
            ),
            account=NavAccountData(
                user=_get_nav_user(user),
                current_workspace=next(
                    (ws for ws in workspaces if ws.is_current), None
                ),
                workspaces=workspaces,
                menu_links=_load_menu_links(is_anonymous),
                logout_href="" if is_anonymous else get_route_path(logout),
                add_workspace_url=add_workspace_url,
                login_href=get_login_url(request) if is_anonymous else "/login/",
            ),
            gooey_builder=_load_gooey_builder_data(request, workspace, page),
        )
    )


def _load_nav_items(
    is_anonymous: bool,
    *,
    home_path: str,
    explore_path: str,
    saved_path: str,
    saved_workflows: list[NavWorkflowItem],
) -> list[NavItemData]:
    explore_item = NavItemData(
        key="explore",
        label="Explore",
        icon="fa-regular fa-magnifying-glass",
        href=explore_path,
    )
    if is_anonymous:
        return [explore_item]
    return [
        NavItemData(
            key="home",
            label="Home",
            icon="fa-regular fa-house",
            href=home_path,
        ),
        explore_item,
        NavItemData(
            key="saved",
            label="Saved",
            icon="fa-regular fa-floppy-disk",
            href=saved_path,
            items=saved_workflows,
        ),
    ]


def _load_menu_links(is_anonymous: bool) -> list[MenuLinkData]:
    public_links = [
        MenuLinkData(label=label, href=url, icon=settings.HEADER_ICONS.get(url))
        for url, label in settings.HEADER_LINKS
        if label != "Explore"
    ]
    if is_anonymous:
        return public_links

    from routers.account import account_route, profile_route

    return [
        MenuLinkData(
            label="Profile",
            href=get_route_path(profile_route),
            icon="fa-regular fa-user",
        ),
        MenuLinkData(
            label="Billing",
            href=get_route_path(account_route),
            icon="fa-regular fa-credit-card",
        ),
        *public_links,
    ]


def _get_nav_user(user: AppUser | None) -> NavUserData | None:
    if user is None:
        return None
    user_name = user.display_name or user.first_name(fallback="User")
    return NavUserData(
        name=user_name,
        photo_url=user.photo_url or None,
    )


def _load_workspaces(
    user: AppUser | None,
    current_workspace: Workspace | None,
) -> list[WorkspaceData]:
    if user is None:
        return []
    workspaces = user.cached_workspaces
    member_counts = _workspace_member_counts(workspaces)
    return [
        WorkspaceData(
            id=ws.id,
            name=ws.display_name(user),
            icon_html=ws.html_icon(),
            subtitle=_workspace_subtitle(ws, member_counts.get(ws.id, 0)),
            is_current=current_workspace is not None and ws.id == current_workspace.id,
            is_personal=ws.is_personal,
        )
        for ws in workspaces
    ]


def _workspace_member_counts(workspaces: list[Workspace]) -> dict[int, int]:
    """Member counts for org workspaces in one query (avoids a COUNT per row)."""
    from django.db.models import Count
    from workspaces.models import WorkspaceMembership

    org_ids = [ws.id for ws in workspaces if not ws.is_personal]
    return dict(
        WorkspaceMembership.objects.filter(
            workspace_id__in=org_ids, deleted__isnull=True
        )
        .values("workspace_id")
        .annotate(n=Count("id"))
        .values_list("workspace_id", "n")
    )


def _load_saved_workflows(
    user: AppUser | None,
    workspace: Workspace | None,
) -> list[NavWorkflowItem]:
    from widgets.home import saved_published_runs

    return [_pr_to_nav_workflow(pr) for pr in saved_published_runs(user, workspace)]


def _load_recent_workflows(
    user: AppUser | None,
    workspace: Workspace | None,
    limit: int = 20,
) -> list[NavWorkflowItem]:
    srs = _recent_run_srs(user, workspace, limit)
    return [_sr_to_nav_workflow(sr) for sr in srs]


def _recent_run_srs(
    user: AppUser | None,
    workspace: Workspace | None,
    limit: int,
) -> list[SavedRun]:
    """Hydrate the recent runs we'll actually render, newest first.

    Split from id selection so we only materialise the ~`limit` rows shown,
    rather than the whole scan window.
    """
    from django.db.models import F
    from bots.models import SavedRun

    ids = _recent_run_ids(user, workspace, limit)
    if not ids:
        return []
    return list(
        SavedRun.objects.filter(id__in=ids)
        .select_related("parent_version__published_run__saved_run")
        .annotate(builder_prompt=F("parent_builder_saved_run__state__input_prompt"))
        .order_by("-updated_at")
    )


def _recent_run_ids(
    user: AppUser | None,
    workspace: Workspace | None,
    limit: int,
) -> list[int]:
    if user is None or workspace is None:
        return []

    from django.db.models import F
    from bots.models import SavedRun
    from widgets.home import RECENT_WORKFLOW_SCAN_LIMIT

    history_runs = (
        SavedRun.objects.filter(
            uid=user.uid, workspace=workspace, surface=SavedRun.Surface.run
        )
        .annotate(published_run_id=F("parent_version__published_run_id"))
        .order_by("-updated_at")
        .values("id", "published_run_id", "updated_at")[:RECENT_WORKFLOW_SCAN_LIMIT]
    )
    builder_runs = (
        SavedRun.objects.filter(
            uid=user.uid, workspace=workspace, surface=SavedRun.Surface.builder_child
        )
        .order_by("-updated_at")
        .values("id", "updated_at")[:limit]
    )

    picked: list[tuple] = []  # (updated_at, id)
    seen_published_runs: set[int | None] = set()
    for row in history_runs:
        if row["published_run_id"] in seen_published_runs:
            continue
        seen_published_runs.add(row["published_run_id"])
        picked.append((row["updated_at"], row["id"]))
        if len(picked) >= limit:
            break
    picked.extend((row["updated_at"], row["id"]) for row in builder_runs)

    picked.sort(key=lambda row: row[0], reverse=True)
    return [id_ for _, id_ in picked[:limit]]


def _sr_to_nav_workflow(sr: SavedRun) -> NavWorkflowItem:
    from bots.models import SavedRun
    from bots.models.workflow import Workflow
    from widgets.home import get_workflow_metadata

    workflow = Workflow(sr.workflow)
    metadata = get_workflow_metadata(workflow)
    pr = sr.parent_published_run()

    if sr.surface == SavedRun.Surface.builder_child:
        title = (sr.builder_prompt or "").strip()
    else:
        title = _history_title(sr, pr, metadata)

    return NavWorkflowItem(
        title=title or (pr and pr.title) or workflow.label,
        href=sr.get_app_url(),
        icon=_workflow_icon(metadata),
        image_url=(pr and pr.photo_url) or None,
    )


def _pr_to_nav_workflow(pr: PublishedRun) -> NavWorkflowItem:
    from bots.models.workflow import Workflow
    from widgets.home import get_workflow_metadata

    workflow = Workflow(pr.workflow)
    metadata = get_workflow_metadata(workflow)
    return NavWorkflowItem(
        title=pr.title or workflow.label,
        href=pr.get_app_url(),
        icon=_workflow_icon(metadata),
        image_url=pr.photo_url or None,
    )


def _history_title(
    sr: SavedRun, pr: PublishedRun | None, metadata: WorkflowMetadata
) -> str:
    from bots.models.workflow import Workflow
    from daras_ai_v2.breadcrumbs import get_title_breadcrumbs

    return get_title_breadcrumbs(
        Workflow(sr.workflow).page_cls, sr, pr, metadata=metadata
    ).title_with_prefix()


def _workflow_icon(metadata) -> str:
    return (metadata and (metadata.fa_icon or metadata.emoji)) or ""


def _load_gooey_builder_data(
    request: Request,
    workspace: Workspace | None,
    page: BasePage | None,
) -> GooeyBuilderData | None:
    from routers.root import RecipeTabs

    if page is None or page.tab not in (RecipeTabs.run, RecipeTabs.preview):
        return None

    from daras_ai_v2.gooey_builder import can_launch_gooey_builder

    if not can_launch_gooey_builder(request, workspace):
        return None

    from bots.models import BotIntegration
    from daras_ai_v2.gooey_builder import DEFAULT_GOOEY_BUILDER_PHOTO_URL

    if not settings.GOOEY_BUILDER_INTEGRATION_ID:
        return None
    try:
        bi = BotIntegration.objects.get(id=settings.GOOEY_BUILDER_INTEGRATION_ID)
    except BotIntegration.DoesNotExist:
        return None
    photo_url = bi.get_web_widget_branding().get(
        "photoUrl", DEFAULT_GOOEY_BUILDER_PHOTO_URL
    )
    return GooeyBuilderData(photo_url=photo_url)


def _active_nav_key(current_path: str, route_paths: dict[str, str]) -> str | None:
    normalized_current = _normalize_path(current_path)
    for key, path in route_paths.items():
        if normalized_current == _normalize_path(path):
            return key
    return None


def _normalize_path(path: str) -> str:
    return path.rstrip("/") or "/"


def _workspace_subtitle(ws, member_count: int) -> str:
    if ws.is_personal:
        return "Personal"
    return f"Org · {member_count} member" + ("" if member_count == 1 else "s")
