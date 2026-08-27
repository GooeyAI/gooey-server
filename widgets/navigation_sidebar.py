from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.requests import Request

import gooey_gui as gui
from daras_ai_v2 import icons, settings
from daras_ai_v2.base import BasePage
from daras_ai_v2.fastapi_tricks import get_route_path
from daras_ai_v2.gooey_builder import (
    GOOEY_BUILDER_EVENT_KEY,
)
from gooey_gui.types.navigation_sidebar_props import (
    BuilderIntent,
    GooeyBuilderData,
    MenuLinkData,
    NavAccountData,
    NavigationSidebarProps,
    NavItemData,
    NavUserData,
    NavWorkflowItem,
    WorkspaceData,
)
from routers.ask_gooey_new import ask_gooey_new_page
from widgets.workflow_queries import (
    recent_run_ids,
    recent_workflow_items,
    saved_published_runs,
)

if TYPE_CHECKING:
    from app_users.models import AppUser
    from bots.models import PublishedRun, SavedRun
    from bots.models.workflow import WorkflowMetadata
    from workspaces.models import Workspace

RECENT_WORKFLOW_LIST_LIMIT = 20
NAV_COLLAPSED_STATE_KEY = "nav-sidebar:default-collapsed"


def render(
    request: Request,
    default_collapsed: bool = False,
    page: BasePage | None = None,
) -> None:
    from routers.base_auth import get_login_url, logout
    from routers.root import explore_page, home_page
    from widgets.history import history_page
    from widgets.home import _saved_workflows_href
    from widgets.workflow_search import get_filter_value_from_workspace
    from workspaces.widgets import (
        SWITCH_WORKSPACE_KEY,
        get_create_workspace_popup_url,
        get_current_workspace,
        handle_workspace_switch,
    )

    new_path = get_route_path(ask_gooey_new_page)
    home_path = get_route_path(home_page)
    explore_path = get_route_path(explore_page)
    history_path = get_route_path(history_page)

    is_anonymous = request.user is None or request.user.is_anonymous
    if is_anonymous:
        user = None
        workspace = None
    else:
        user = request.user
        handle_workspace_switch(request.session)
        _refresh_workspace_cache(user)
        workspace = get_current_workspace(user, request.session)

    saved_path = _saved_workflows_href(workspace)
    workspaces = _load_workspaces(user, workspace)

    if workspace is None:
        saved_workspace_filter = None
    else:
        saved_workspace_filter = get_filter_value_from_workspace(workspace)

    active_key = _active_nav_key(
        request,
        new_path=new_path,
        home_path=home_path,
        explore_path=explore_path,
        history_path=history_path,
        saved_workspace_filter=saved_workspace_filter,
    )

    if is_anonymous:
        add_workspace_url = ""
    else:
        add_workspace_url, _ = get_create_workspace_popup_url()

    gui.model_component(
        NavigationSidebarProps(
            logo_image_url=settings.GOOEY_LOGO_IMG,
            logo_href=settings.APP_BASE_URL,
            nav_items=_load_nav_items(
                is_anonymous,
                new_path=new_path,
                home_path=home_path,
                explore_path=explore_path,
                saved_path=saved_path,
                history_path=history_path,
                saved_workflows=_load_saved_workflows(user, workspace),
                history_items_url=get_route_path(recent_workflow_items),
                history_cache_key=_history_cache_key(user, workspace),
            ),
            active_key=active_key,
            collapsed_state_key=NAV_COLLAPSED_STATE_KEY,
            default_collapsed=default_collapsed,
            account=NavAccountData(
                user=_get_nav_user(user),
                current_workspace=next(
                    (ws for ws in workspaces if ws.is_current), None
                ),
                workspaces=workspaces,
                switch_workspace_key=SWITCH_WORKSPACE_KEY,
                menu_links=_load_menu_links(is_anonymous, workspace),
                logout_href="" if is_anonymous else get_route_path(logout),
                add_workspace_url=add_workspace_url,
                login_href=get_login_url(request) if is_anonymous else "/login/",
                enable_firebase_auth=settings.ENABLE_FIREBASE_AUTH,
            ),
            gooey_builder=_load_gooey_builder_data(request, workspace, page),
        )
    )


def _refresh_workspace_cache(user: AppUser) -> None:
    try:
        del user.cached_workspaces
    except AttributeError:
        pass


def _load_nav_items(
    is_anonymous: bool,
    *,
    new_path: str,
    home_path: str,
    explore_path: str,
    saved_path: str,
    history_path: str,
    saved_workflows: list[NavWorkflowItem],
    history_items_url: str,
    history_cache_key: str | None,
) -> list[NavItemData]:
    explore_item = NavItemData(
        key="explore",
        label="Explore",
        icon=icons.explore,
        href=explore_path,
    )
    if is_anonymous:
        return [explore_item]
    items = [
        NavItemData(
            key="new",
            label="New",
            icon=icons.add,
            href=new_path,
        ),
        NavItemData(
            key="home",
            label="Home",
            icon=icons.home,
            href=home_path,
        ),
        explore_item,
        NavItemData(
            key="saved",
            label="Saved",
            icon=icons.save,
            href=saved_path,
            items=saved_workflows,
        ),
    ]
    items.append(
        NavItemData(
            key="history",
            label="History",
            icon=icons.history,
            items_url=history_items_url,
            items_cache_key=history_cache_key,
            collapsible=False,
            dense=True,
        )
    )
    return items


def _history_cache_key(
    user: AppUser | None,
    workspace: Workspace | None,
) -> str | None:
    if user is None or workspace is None:
        return None
    # runs are per-user within a workspace, and the uid is already public (it's a
    # query param on every run url)
    return f"{user.uid}:{workspace.id}"


def _load_menu_links(
    is_anonymous: bool,
    workspace: Workspace | None,
) -> list[MenuLinkData]:
    public_links = [
        MenuLinkData(label=label, href=url, icon=settings.HEADER_ICONS.get(url))
        for url, label in settings.HEADER_LINKS
        if label != "Explore"
    ]
    if is_anonymous:
        return public_links

    from routers.account import account_route, profile_route

    links = []
    # Profile settings are per-user, so only surface them in a personal workspace.
    if workspace is not None and workspace.is_personal:
        links.append(
            MenuLinkData(
                label="Profile",
                href=get_route_path(profile_route),
                icon=icons.cls.user,
            )
        )
    links.append(
        MenuLinkData(
            label="Billing",
            href=get_route_path(account_route),
            icon=icons.cls.credit_card,
        )
    )
    # Pricing targets logged-out visitors; signed-in users manage spend via Billing.
    links += [link for link in public_links if link.label != "Pricing"]
    return links


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
            icon_html=ws.html_icon(size="30px"),
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
    return [_pr_to_nav_workflow(pr) for pr in saved_published_runs(user, workspace)]


def load_recent_workflow_items(
    user: AppUser | None,
    workspace: Workspace | None,
    limit: int = RECENT_WORKFLOW_LIST_LIMIT,
) -> list[NavWorkflowItem]:
    """Recent runs for the sidebar History section.

    Called from the `recent_workflow_items` endpoint rather than
    during render, so these queries stay off the page's critical path.
    """
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

    ids = recent_run_ids(
        user,
        workspace,
        limit,
        include_builder_runs=True,
    )
    if not ids:
        return []
    return list(
        SavedRun.objects.filter(id__in=ids)
        .select_related("parent_version__published_run__saved_run", "workflow_metadata")
        .annotate(
            builder_thread_title=F(
                "parent_builder_saved_run__thread_as_last_run__title"
            ),
            # title of a standalone builder conversation's own thread
            builder_prompt_title=F("thread_as_last_run__title"),
        )
        .order_by("-updated_at")
    )


def _sr_to_nav_workflow(sr: SavedRun) -> NavWorkflowItem:
    from bots.models import SavedRun
    from bots.models.workflow import Workflow

    workflow = Workflow(sr.workflow)
    metadata = sr.get_workflow_metadata()
    pr = sr.parent_published_run()

    builder_intent: BuilderIntent | None = None
    if sr.surface == SavedRun.Surface.builder_child:
        title = (sr.builder_thread_title or "").strip()
        # Only Builder runs opened from the rail force-open the Builder panel.
        builder_intent = "open"
        href = sr.get_app_url()
    elif sr.surface == SavedRun.Surface.builder_prompt:
        # standalone builder conversation -> the /new/ page for this run
        from routers.ask_gooey_new import get_gooey_builder_run_url

        title = (sr.builder_prompt_title or "").strip()
        href = get_gooey_builder_run_url(sr)
    else:
        title = _history_title(sr, pr)
        href = sr.get_app_url()

    return NavWorkflowItem(
        title=title or (pr and pr.title) or workflow.label,
        href=href,
        image_url=(pr and pr.photo_url) or None,
        icon=_workflow_icon(metadata),
        builder_intent=builder_intent,
    )


def _pr_to_nav_workflow(pr: PublishedRun) -> NavWorkflowItem:
    from bots.models.workflow import Workflow

    workflow = Workflow(pr.workflow)
    metadata = pr.get_workflow_metadata()
    return NavWorkflowItem(
        title=pr.title or workflow.label,
        href=pr.get_app_url(),
        image_url=pr.photo_url or None,
        icon=_workflow_icon(metadata),
    )


def _history_title(sr: SavedRun, pr: PublishedRun | None) -> str:
    from bots.models.workflow import Workflow
    from daras_ai_v2.breadcrumbs import get_title_breadcrumbs

    return get_title_breadcrumbs(
        Workflow(sr.workflow).page_cls, sr, pr
    ).title_with_prefix()


def _workflow_icon(metadata: WorkflowMetadata | None) -> str:
    return (metadata and (metadata.fa_icon or metadata.emoji)) or ""


def _load_gooey_builder_data(
    request: Request,
    workspace: Workspace | None,
    page: BasePage | None,
) -> GooeyBuilderData | None:
    from routers.root import RecipeTabs

    from routers.root import _is_layout_v2_page

    # v2 keeps the Builder available on every tab and pane of the recipe page; v1 only
    # offers it on Run/Preview.
    if page is None:
        return None
    is_v2 = _is_layout_v2_page(page)
    if not is_v2 and page.tab not in (
        RecipeTabs.run,
        RecipeTabs.preview,
    ):
        return None

    from daras_ai_v2.gooey_builder import can_launch_gooey_builder

    if not can_launch_gooey_builder(request, workspace):
        return None

    from daras_ai_v2.gooey_builder import (
        get_gooey_builder_integration,
        get_gooey_builder_photo_url,
    )

    bi = get_gooey_builder_integration()
    if bi is None:
        return None
    return GooeyBuilderData(
        # shared with the Builder panel's own title button, so the rail and the panel cannot
        # end up showing different avatars
        photo_url=get_gooey_builder_photo_url(bi),
        name=bi.name,
        event_key=GOOEY_BUILDER_EVENT_KEY,
        storage_key=(f"{page._workspace_storage_key()}:builder" if is_v2 else None),
    )


def _active_nav_key(
    request: Request,
    *,
    new_path: str,
    home_path: str,
    explore_path: str,
    history_path: str,
    saved_workspace_filter: str | None,
) -> str | None:
    current = _normalize_path(request.url.path)

    if current == _normalize_path(new_path):
        return "new"

    if current == _normalize_path(explore_path):
        # Saved is Explore scoped to the current workspace: both live at
        # /explore/ and differ only by the ?workspace= filter, so disambiguate
        # on that query param (request.url.path drops the query string).
        if (
            saved_workspace_filter
            and request.query_params.get("workspace") == saved_workspace_filter
        ):
            return "saved"
        return "explore"

    if current == _normalize_path(home_path):
        return "home"
    if current == _normalize_path(history_path):
        return "history"
    return None


def _normalize_path(path: str) -> str:
    return path.rstrip("/") or "/"


def _workspace_subtitle(ws: Workspace, member_count: int) -> str:
    if ws.is_personal:
        return "Personal"
    return f"Org · {member_count} member" + ("" if member_count == 1 else "s")
