from __future__ import annotations

import typing
from datetime import datetime


import gooey_gui as gui
from django.db.models import Count, OuterRef, Q, Subquery, F
from django.utils import timezone
from furl import furl
from starlette.requests import Request

from app_users.models import AppUser
from bots.models import PublishedRun, PublishedRunVersion, SavedRun
from bots.models.published_run import Tag
from bots.models.workflow import WorkflowAccessLevel, WorkflowMetadata
from cms.models import NewsItem
from daras_ai_v2.meta_content import raw_build_meta_tags
from gooey_gui.types.home_page_props import (
    IndustryTileData,
    NewsItemData,
    WorkflowCardData,
    WorkflowTabData,
    WorkspaceHeaderData,
    HomePageProps,
)
from widgets.workflow_cards import (
    author_from_user,
    author_from_workspace,
    pr_to_card,
    saved_card,
    history_card,
)
from widgets.workflow_search import get_filter_value_from_workspace
from workspaces.models import Workspace
from workspaces.widgets import get_current_workspace


META_TITLE = "Home | Gooey.AI"
META_DESCRIPTION = "Build AI workflows on Gooey.AI"

WORKFLOW_LIST_LIMIT = 3
RECENT_WORKFLOW_LIST_LIMIT = 4
RECENT_WORKFLOW_SCAN_LIMIT = 200
NEWS_ITEM_LIST_LIMIT = 4


def render(request: Request):
    is_anonymous = request.user is None or request.user.is_anonymous
    if is_anonymous:
        workspace = None
    else:
        workspace = get_current_workspace(request.user, request.session)
    workspace_header = _get_workspace_header(request.user, workspace)
    if not is_anonymous and workspace_header is None:
        greeting = _get_greeting(request.user)
    else:
        greeting = None

    gui.model_component(
        HomePageProps(
            greeting=greeting,
            workspace_header=workspace_header,
            workflow_tabs=list(_load_workflow_tabs()),
            recent_workflows=_load_recent_workflows(request.user, workspace),
            recent_workflows_href=_recent_workflows_href(),
            saved_workflows=_load_saved_workflows(request.user, workspace),
            saved_workflows_href=_saved_workflows_href(workspace),
            industry_tiles=_load_industry_tiles(),
            news_items=_load_news_items(),
        ),
    )


def _get_workspace_header(
    user: AppUser | None, workspace: Workspace | None
) -> WorkspaceHeaderData | None:
    if user is None or workspace is None or workspace.is_personal:
        return None

    from routers.account import members_route
    from daras_ai_v2.fastapi_tricks import get_route_path

    membership = workspace.memberships.filter(user=user).first()
    settings_href = (
        get_route_path(members_route)
        if membership and membership.can_edit_workspace()
        else None
    )
    return WorkspaceHeaderData(
        name=workspace.display_name(user),
        photo_url=workspace.get_photo(),
        description=workspace.description or None,
        settings_href=settings_href,
    )


def build_meta_tags(url: str):
    return raw_build_meta_tags(
        url=url,
        title=META_TITLE,
        description=META_DESCRIPTION,
    )


def _get_greeting(user: AppUser) -> str | None:
    return user.first_name(fallback="") or None


def _load_recent_workflows(
    user: AppUser | None,
    workspace: Workspace | None,
    limit: int = RECENT_WORKFLOW_LIST_LIMIT,
) -> list[WorkflowCardData]:
    if user is None or workspace is None:
        return []

    qs = (
        SavedRun.objects.filter(
            uid=user.uid, workspace=workspace, surface=SavedRun.Surface.run
        )
        .annotate(published_run_id=F("parent_version__published_run_id"))
        .order_by("-updated_at")
        .values("id", "published_run_id")[:RECENT_WORKFLOW_SCAN_LIMIT]
    )
    ids = []
    seen_published_runs = set()
    for sr in qs:
        if sr["published_run_id"] in seen_published_runs:
            continue
        seen_published_runs.add(sr["published_run_id"])
        ids.append(sr["id"])
        if len(ids) >= limit:
            break

    return [
        history_card(sr, author=author_from_user(user, current_user=user))
        for sr in SavedRun.objects.select_related(
            "parent_version__published_run", "workflow_metadata"
        )
        .filter(id__in=ids)
        .order_by("-updated_at")
    ]


def _load_saved_workflows(
    user: AppUser | None,
    workspace: Workspace | None,
) -> list[WorkflowCardData]:
    if user is None or workspace is None:
        return []
    pr_filter = Q(workspace=workspace)
    if workspace.is_personal:
        pr_filter |= Q(created_by=user)
    latest_change_notes = (
        PublishedRunVersion.objects.filter(published_run=OuterRef("pk"))
        .order_by("-created_at")
        .values("change_notes")[:1]
    )
    prs = list(
        PublishedRun.objects.filter(pr_filter)
        .select_related("last_edited_by", "saved_run", "workspace", "workflow_metadata")
        .annotate(latest_change_notes=Subquery(latest_change_notes))
        .order_by("-updated_at")[:WORKFLOW_LIST_LIMIT]
    )
    return [
        saved_card(
            pr,
            author=author_from_user(pr.last_edited_by, current_user=user),
        )
        for pr in prs
    ]


def _load_workflow_tabs() -> typing.Iterable[WorkflowTabData]:
    featured_workflows = (
        WorkflowMetadata.objects.filter(is_featured=True)
        .order_by("-priority")
        .values_list("workflow", flat=True)
    )
    pr_qs = (
        PublishedRun.objects.select_related(
            "workspace__created_by", "saved_run", "workflow_metadata"
        )
        .filter(is_featured=True, workflow__in=featured_workflows)
        .order_by("-example_priority")
    )
    grouped = {workflow: [] for workflow in featured_workflows}
    for pr in pr_qs:
        try:
            grouped[pr.workflow].append(pr)
        except KeyError:
            pass
    for workflow, pr_group in grouped.items():
        if not pr_group:
            continue
        metadata = pr_group[0].get_workflow_metadata()
        yield WorkflowTabData(
            id=metadata.workflow,
            title=metadata.short_title,
            icon=metadata.tab_icon_html(),
            cards=[
                pr_to_card(pr, author=author_from_workspace(pr.workspace))
                for pr in pr_group
            ],
        )


def _load_industry_tiles() -> list[IndustryTileData]:
    qs = (
        Tag.objects.filter(is_featured=True, hidden=False)
        .annotate(
            workflow_count=Count(
                "published_runs",
                filter=Q(
                    published_runs__public_access__gt=WorkflowAccessLevel.VIEW_ONLY,
                    published_runs__is_approved_example=True,
                ),
                distinct=True,
            ),
        )
        .order_by("-featured_priority")
    )
    return [
        IndustryTileData(
            id=tag.id,
            name=tag.name,
            icon=tag.fa_icon or tag.icon,
            color=tag.color or None,
            description=tag.description,
            workflow_count=tag.workflow_count,
            href=_industry_tile_href(tag),
        )
        for tag in qs
    ]


def _recent_workflows_href() -> str:
    from daras_ai_v2.fastapi_tricks import get_route_path
    from widgets.history import history_page

    return get_route_path(history_page)


def _saved_workflows_href(workspace: Workspace | None) -> str:
    if workspace is None:
        return "/explore/"
    return str(
        furl(
            "/explore/",
            query_params={"workspace": get_filter_value_from_workspace(workspace)},
        )
    )


def _industry_tile_href(tag: Tag) -> str:
    if tag.landing_page:
        return tag.landing_page
    return str(furl("/explore/", query_params={"search": tag.name}))


def _load_news_items() -> list[NewsItemData]:
    qs = NewsItem.objects.filter(publish_date__lte=timezone.now()).order_by(
        "-publish_date"
    )[:NEWS_ITEM_LIST_LIMIT]
    return [
        NewsItemData(
            id=item.id,
            headline=item.headline,
            tag=item.tag,
            photo_url=item.photo_url or None,
            publish_date=_format_news_date(item.publish_date),
            href=item.url,
        )
        for item in qs
    ]


def _format_news_date(publish_date: datetime) -> str:
    label = publish_date.strftime("%-d %b").upper()
    if publish_date.year != timezone.now().year:
        label += f" {publish_date.year}"
    return label
