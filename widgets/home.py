from datetime import date

import gooey_gui as gui
from django.db.models import Count, Prefetch, Q
from furl import furl
from starlette.requests import Request

from app_users.models import AppUser
from bots.models import PublishedRun, SavedRun, Workflow
from bots.models.workflow import WorkflowAccessLevel
from cms.models import IndustryTile, NewsItem, WorkflowCard, WorkflowTab
from daras_ai_v2.meta_content import raw_build_meta_tags
from daras_ai_v2.utils import get_relative_time
from workspaces.models import Workspace
from workspaces.widgets import get_current_workspace

META_TITLE = "Home | Gooey.AI"
META_DESCRIPTION = "Build AI workflows on Gooey.AI"

WORKFLOW_LIST_LIMIT = 3


def render(request: Request):
    is_anonymous = request.user is None or request.user.is_anonymous
    workspace = (
        get_current_workspace(request.user, request.session)
        if not is_anonymous
        else None
    )
    gui.component(
        "HomePage",
        greeting=_get_greeting(request.user) if not is_anonymous else None,
        workflowTabs=_load_workflow_tabs(),
        recentWorkflows=_load_recent_workflows(request.user, workspace),
        savedWorkflows=_load_saved_workflows(request.user, workspace),
        industryTiles=_load_industry_tiles(),
        newsItems=_load_news_items(),
    )


def build_meta_tags(url: str):
    return raw_build_meta_tags(
        url=url,
        title=META_TITLE,
        description=META_DESCRIPTION,
    )


def _get_greeting(user: AppUser) -> str | None:
    return user.first_name(fallback="") or None


def _load_workflow_tabs() -> list[dict]:
    qs = WorkflowTab.objects.prefetch_related(
        Prefetch(
            "cards",
            queryset=WorkflowCard.objects.select_related(
                "recipe__workspace__created_by"
            ).order_by("order"),
        )
    ).order_by("order")
    return [
        {
            "id": tab.id,
            "title": tab.title,
            "icon": tab.icon,
            "cards": [
                {
                    "id": card.id,
                    "title": card.recipe.title or "Untitled",
                    "description": card.recipe.notes,
                    "authorName": card.recipe.workspace.display_name(),
                    "authorPhotoUrl": card.recipe.workspace.get_photo() or None,
                    "imageUrl": card.recipe.photo_url or None,
                    "href": card.recipe.get_app_url(),
                }
                for card in tab.cards.all()
            ],
        }
        for tab in qs
    ]


def _load_recent_workflows(
    user: AppUser | None, workspace: Workspace | None
) -> list[dict]:
    if workspace is None:
        return []
    # Latest saved run per parent published run: the inner DISTINCT ON
    # queryset is used as a subquery (no `list(...)` so it isn't evaluated
    # eagerly), then re-ordered overall by recency and limited.
    latest_ids = (
        SavedRun.objects.filter(
            workspace=workspace,
            parent_version__published_run__isnull=False,
        )
        .order_by("parent_version__published_run_id", "-updated_at")
        .distinct("parent_version__published_run_id")
        .values("id")
    )
    saved_runs = (
        SavedRun.objects.filter(id__in=latest_ids)
        .select_related("parent_version__published_run")
        .order_by("-updated_at")[:WORKFLOW_LIST_LIMIT]
    )
    current_uid = user and user.uid
    authors_by_uid = _fetch_authors_by_uid(
        {sr.uid for sr in saved_runs if sr.uid and sr.uid != current_uid}
    )
    return [
        _workflow_item(
            row_id=sr.id,
            title=_pr_title(sr.parent_published_run(), sr.workflow),
            workflow=sr.workflow,
            author=authors_by_uid.get(sr.uid) if sr.uid != current_uid else None,
            image_url=(sr.parent_version and sr.parent_version.published_run.photo_url)
            or None,
            updated_at=sr.updated_at,
            href=sr.get_app_url(),
        )
        for sr in saved_runs
    ]


def _load_saved_workflows(
    user: AppUser | None, workspace: Workspace | None
) -> list[dict]:
    if user is None or workspace is None:
        return []
    pr_filter = Q(workspace=workspace)
    if workspace.is_personal:
        pr_filter |= Q(created_by=user, workspace__isnull=True)
    qs = (
        PublishedRun.objects.filter(pr_filter)
        .select_related("last_edited_by")
        .order_by("-updated_at")[:WORKFLOW_LIST_LIMIT]
    )
    return [
        _workflow_item(
            row_id=pr.id,
            title=pr.title or Workflow(pr.workflow).label,
            workflow=pr.workflow,
            author=pr.last_edited_by if pr.last_edited_by_id != user.id else None,
            image_url=pr.photo_url or None,
            updated_at=pr.updated_at,
            href=pr.get_app_url(),
        )
        for pr in qs
    ]


def _pr_title(pr: PublishedRun | None, workflow: int) -> str:
    return (pr and pr.title) or Workflow(workflow).label


def _fetch_authors_by_uid(uids: set[str]) -> dict[str, AppUser]:
    if not uids:
        return {}
    return {u.uid: u for u in AppUser.objects.filter(uid__in=uids)}


def _workflow_item(
    *,
    row_id: int,
    title: str,
    workflow: int,
    author: AppUser | None,
    image_url: str | None,
    updated_at,
    href: str,
) -> dict:
    return {
        "id": row_id,
        "title": title,
        "workflowLabel": Workflow(workflow).label,
        "authorName": (author and author.display_name) or "",
        "authorPhotoUrl": (author and author.photo_url) or None,
        "imageUrl": image_url,
        "updatedAt": get_relative_time(updated_at) if updated_at else "",
        "href": href,
    }


def _load_industry_tiles() -> list[dict]:
    qs = (
        IndustryTile.objects.select_related("tag")
        .annotate(
            workflow_count=Count(
                "tag__published_runs",
                filter=Q(
                    tag__published_runs__public_access__gt=WorkflowAccessLevel.VIEW_ONLY,
                    tag__published_runs__is_approved_example=True,
                ),
                distinct=True,
            ),
        )
        .order_by("order")
    )
    return [
        {
            "id": tile.id,
            "tagId": tile.tag_id,
            "name": tile.tag.name,
            "icon": tile.tag.icon,
            "description": tile.tag.description,
            "workflowCount": tile.workflow_count,
            "href": str(furl("/explore/", query_params={"search": tile.tag.name})),
        }
        for tile in qs
    ]


def _load_news_items() -> list[dict]:
    qs = NewsItem.objects.filter(publish_date__lte=date.today()).order_by(
        "-publish_date"
    )[:4]
    return [
        {
            "id": item.id,
            "headline": item.headline,
            "tag": item.tag,
            "photoUrl": item.photo_url or None,
            "age": _format_news_age(item.publish_date),
            "href": item.url,
        }
        for item in qs
    ]


def _format_news_age(publish_date: date) -> str:
    delta_days = (date.today() - publish_date).days
    if delta_days < 7:
        return f"{delta_days}d"
    if delta_days < 30:
        return f"{delta_days // 7}w"
    if delta_days < 365:
        return f"{delta_days // 30}mo"
    return f"{delta_days // 365}y"
