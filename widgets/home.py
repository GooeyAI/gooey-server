from __future__ import annotations

import mimetypes
from typing import TYPE_CHECKING, TypedDict

import gooey_gui as gui
from django.db.models import Count, OuterRef, Prefetch, Q, Subquery
from django.utils import timezone
from furl import furl
from pydantic import BaseModel
from starlette.requests import Request

from app_users.models import AppUser
from bots.models import PublishedRun, PublishedRunVersion, SavedRun, Workflow
from bots.models.workflow import WorkflowAccessLevel, WorkflowMetadata
from cms.models import IndustryTile, NewsItem, WorkflowCard, WorkflowTab
from daras_ai.image_input import truncate_text_words
from daras_ai_v2.meta_content import raw_build_meta_tags
from daras_ai_v2.preview_img import media_preview_img
from daras_ai_v2.utils import get_relative_time
from workspaces.models import Workspace
from workspaces.widgets import get_current_workspace

if TYPE_CHECKING:
    from daras_ai_v2.base import BasePage

# request-scoped cache of Workflow value -> its metadata row (or None when the
# workflow has none), populated lazily so each workflow is queried at most once
# per render instead of once per card.
MetadataByWorkflow = dict[Workflow, WorkflowMetadata | None]

META_TITLE = "Home | Gooey.AI"
META_DESCRIPTION = "Build AI workflows on Gooey.AI"

WORKFLOW_LIST_LIMIT = 3
RECENT_WORKFLOW_LIST_LIMIT = 4
NEWS_ITEM_LIST_LIMIT = 4

CHAT_PREVIEW_MAXLEN = 130
MEDIA_CAPTION_MAXLEN = 60


class AccessBadgeData(TypedDict):
    iconHtml: str
    label: str


class WorkflowCardData(TypedDict, total=False):
    title: str
    href: str
    workflowEmoji: str
    description: str
    authorName: str
    authorPhotoUrl: str | None
    preview: dict
    updatedAt: str
    runCount: int
    accessBadge: AccessBadgeData
    changeNotes: str


class WorkflowTabData(TypedDict):
    id: int
    title: str
    icon: str
    cards: list[WorkflowCardData]


class WorkspaceHeaderData(TypedDict):
    name: str
    photoUrl: str
    description: str | None
    settingsHref: str | None


def render(request: Request):
    is_anonymous = request.user is None or request.user.is_anonymous
    workspace = (
        get_current_workspace(request.user, request.session)
        if not is_anonymous
        else None
    )
    workspace_header = _get_workspace_header(request.user, workspace)
    metadata_by_workflow: MetadataByWorkflow = {}
    gui.component(
        "HomePage",
        greeting=(
            _get_greeting(request.user)
            if not is_anonymous and workspace_header is None
            else None
        ),
        workspaceHeader=workspace_header,
        recentWorkflows=_load_recent_workflows(
            request.user, workspace, metadata_by_workflow
        ),
        savedWorkflows=_load_saved_workflows(
            request.user, workspace, metadata_by_workflow
        ),
        workflowTabs=_load_workflow_tabs(metadata_by_workflow),
        industryTiles=_load_industry_tiles(),
        newsItems=_load_news_items(),
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
    return {
        "name": workspace.display_name(user),
        "photoUrl": workspace.get_photo(),
        "description": workspace.description or None,
        "settingsHref": settings_href,
    }


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
    metadata_by_workflow: MetadataByWorkflow,
) -> list[WorkflowCardData]:
    if workspace is None:
        return []
    runs = SavedRun.objects.filter(
        workspace=workspace,
        parent_version__published_run__isnull=False,
    )
    if user and not workspace.is_personal:
        # in a team workspace, show only the current user's history
        runs = runs.filter(uid=user.uid)
    latest_ids = (
        runs.order_by("parent_version__published_run_id", "-updated_at")
        .distinct("parent_version__published_run_id")
        .values("id")
    )
    saved_runs = list(
        SavedRun.objects.filter(id__in=latest_ids)
        .select_related("parent_version__published_run")
        .order_by("-updated_at")[:RECENT_WORKFLOW_LIST_LIMIT]
    )
    other_uids = {
        sr.uid for sr in saved_runs if sr.uid and (not user or sr.uid != user.uid)
    }
    authors_by_uid = {u.uid: u for u in AppUser.objects.filter(uid__in=other_uids)}
    return [
        _history_card(
            sr,
            author=author_from_user(
                _history_author(sr, user=user, authors_by_uid=authors_by_uid),
                current_user=user,
            ),
            metadata_by_workflow=metadata_by_workflow,
        )
        for sr in saved_runs
    ]


def _history_author(
    sr: SavedRun,
    *,
    user: AppUser | None,
    authors_by_uid: dict[str, AppUser],
) -> AppUser | None:
    if user and sr.uid == user.uid:
        return user
    if sr.uid:
        return authors_by_uid.get(sr.uid)
    return None


def _load_saved_workflows(
    user: AppUser | None,
    workspace: Workspace | None,
    metadata_by_workflow: MetadataByWorkflow,
) -> list[WorkflowCardData]:
    if user is None or workspace is None:
        return []
    pr_filter = Q(workspace=workspace)
    if workspace.is_personal:
        pr_filter |= Q(created_by=user, workspace__isnull=True)
    latest_change_notes = (
        PublishedRunVersion.objects.filter(published_run=OuterRef("pk"))
        .order_by("-created_at")
        .values("change_notes")[:1]
    )
    prs = list(
        PublishedRun.objects.filter(pr_filter)
        .select_related("last_edited_by", "saved_run", "workspace")
        .annotate(latest_change_notes=Subquery(latest_change_notes))
        .order_by("-updated_at")[:WORKFLOW_LIST_LIMIT]
    )
    return [
        _saved_card(
            pr,
            author=author_from_user(pr.last_edited_by, current_user=user),
            metadata_by_workflow=metadata_by_workflow,
        )
        for pr in prs
    ]


def _load_workflow_tabs(
    metadata_by_workflow: MetadataByWorkflow,
) -> list[WorkflowTabData]:
    qs = (
        WorkflowTab.objects.filter(priority__gte=1)
        .prefetch_related(
            Prefetch(
                "cards",
                queryset=WorkflowCard.objects.filter(priority__gte=1)
                .select_related(
                    "recipe__workspace__created_by",
                    "recipe__saved_run",
                )
                .order_by("-priority"),
            )
        )
        .order_by("-priority")
    )
    return [
        {
            "id": tab.id,
            "title": tab.title,
            "icon": tab.icon,
            "cards": [
                pr_to_json(
                    card.recipe,
                    author=author_from_workspace(card.recipe.workspace),
                    metadata_by_workflow=metadata_by_workflow,
                )
                for card in tab.cards.all()
            ],
        }
        for tab in qs
    ]


class AuthorData(BaseModel):
    name: str
    photo_url: str | None = None


def author_from_user(
    user: AppUser | None, current_user: AppUser | None
) -> AuthorData | None:
    if user is None:
        return None
    if current_user is not None and user.uid == current_user.uid:
        return AuthorData(name="You", photo_url=current_user.photo_url or None)
    return AuthorData(name=user.display_name or "", photo_url=user.photo_url or None)


def author_from_workspace(workspace: Workspace) -> AuthorData:
    return AuthorData(
        name=workspace.display_name(),
        photo_url=workspace.get_photo() or None,
    )


def _history_card(
    sr: SavedRun,
    *,
    author: AuthorData | None,
    metadata_by_workflow: MetadataByWorkflow,
) -> WorkflowCardData:
    data = sr_to_json(sr, author=author, metadata_by_workflow=metadata_by_workflow)
    if sr.updated_at:
        data["updatedAt"] = get_relative_time(sr.updated_at)
    return data


def _saved_card(
    pr: PublishedRun,
    *,
    author: AuthorData | None,
    metadata_by_workflow: MetadataByWorkflow,
) -> WorkflowCardData:
    data = pr_to_json(pr, author=author, metadata_by_workflow=metadata_by_workflow)
    if pr.updated_at:
        data["updatedAt"] = get_relative_time(pr.updated_at)
    if pr.run_count:
        data["runCount"] = pr.run_count
    data["accessBadge"] = pr.get_share_badge_data()
    change_notes = getattr(pr, "latest_change_notes", None)
    if change_notes:
        data["changeNotes"] = change_notes
    return data


def sr_to_json(
    sr: SavedRun,
    *,
    author: AuthorData | None,
    metadata_by_workflow: MetadataByWorkflow,
) -> WorkflowCardData:
    parent_pr = sr.parent_published_run()
    workflow = Workflow(sr.workflow)
    metadata = _get_workflow_metadata(workflow, metadata_by_workflow)
    data: WorkflowCardData = {
        "title": (parent_pr and parent_pr.title) or workflow.label,
        "href": sr.get_app_url(),
        "workflowEmoji": (metadata.emoji if metadata else "") or "",
        **_author_fields(author),
    }
    notes = parent_pr and parent_pr.notes
    if notes:
        data["description"] = notes
    preview = _sr_preview(workflow=workflow, sr=sr, pr=parent_pr, metadata=metadata)
    if preview is not None:
        data["preview"] = preview
    return data


def pr_to_json(
    pr: PublishedRun,
    *,
    author: AuthorData | None,
    metadata_by_workflow: MetadataByWorkflow,
) -> WorkflowCardData:
    workflow = Workflow(pr.workflow)
    metadata = _get_workflow_metadata(workflow, metadata_by_workflow)
    data: WorkflowCardData = {
        "title": pr.title or workflow.label,
        "href": pr.get_app_url(),
        **_author_fields(author),
    }
    if pr.notes:
        data["description"] = pr.notes
    preview = _pr_preview(pr, workflow=workflow, metadata=metadata)
    if preview is not None:
        data["preview"] = preview
    return data


def _author_fields(author: AuthorData | None) -> WorkflowCardData:
    if author is None:
        return {}
    return {"authorName": author.name, "authorPhotoUrl": author.photo_url}


def _get_workflow_metadata(
    workflow: Workflow, cache: MetadataByWorkflow
) -> WorkflowMetadata | None:
    if workflow not in cache:
        cache[workflow] = workflow.get_metadata()
    return cache[workflow]


def _sr_preview(
    *,
    workflow: Workflow,
    sr: SavedRun,
    pr: PublishedRun | None,
    metadata: WorkflowMetadata | None,
) -> dict | None:
    state = sr.state

    if workflow == Workflow.VIDEO_BOTS:
        chat = _chat_preview(state)
        if chat:
            return chat

    page_cls: type[BasePage] = workflow.page_cls
    output_url = page_cls.preview_output(state) or (pr and pr.photo_url) or None
    if output_url:
        return _media_preview(output_url=output_url, state=state, page_cls=page_cls)

    return _icon_preview(metadata)


def _pr_preview(
    pr: PublishedRun,
    *,
    workflow: Workflow,
    metadata: WorkflowMetadata | None,
) -> dict | None:
    if pr.photo_url:
        return _media_preview(output_url=pr.photo_url, caption=None)

    page_cls: type[BasePage] = workflow.page_cls
    state = pr.saved_run.state if pr.saved_run_id else {}
    output_url = page_cls.preview_output(state) if state else None
    if output_url:
        return _media_preview(output_url=output_url, state=state, page_cls=page_cls)

    return _icon_preview(metadata)


def _icon_preview(metadata: WorkflowMetadata | None) -> dict | None:
    if not metadata or not (metadata.default_image or metadata.emoji):
        return None
    return {
        "type": "icon",
        "imageUrl": metadata.default_image or None,
        "emoji": metadata.emoji or None,
    }


def _chat_preview(state: dict) -> dict | None:
    user_message = state.get("input_prompt") or state.get("raw_input_text")
    output_text = state.get("output_text") or []
    bot_message = output_text[0] if output_text else None
    if not user_message and not bot_message:
        return None
    return {
        "type": "chat",
        "userMessage": _preview_text(user_message, CHAT_PREVIEW_MAXLEN),
        "botMessage": _preview_text(bot_message, CHAT_PREVIEW_MAXLEN),
    }


def _media_preview(
    *,
    output_url: str,
    state: dict | None = None,
    page_cls: type[BasePage] | None = None,
    caption: str | None = None,
) -> dict:
    if caption is None and page_cls is not None and state is not None:
        caption = _preview_text(page_cls.preview_input(state), MEDIA_CAPTION_MAXLEN)
    content_type = mimetypes.guess_type(output_url)[0] or ""
    if content_type.startswith("video/"):
        media_type = "video"
    elif content_type.startswith("audio/"):
        media_type = "audio"
    else:
        media_type = "image"
    return {
        "type": media_type,
        "url": output_url,
        "previewImg": media_preview_img(output_url),
        "caption": caption,
    }


def _preview_text(text: str | None, maxlen: int) -> str | None:
    if not text:
        return None
    return truncate_text_words(text, maxlen=maxlen).replace("\n", " ")


def _load_industry_tiles() -> list[dict]:
    qs = (
        IndustryTile.objects.filter(priority__gte=1)
        .select_related("tag")
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
        .order_by("-priority")
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
    qs = NewsItem.objects.filter(publish_date__lte=timezone.now()).order_by(
        "-publish_date"
    )[:NEWS_ITEM_LIST_LIMIT]
    return [
        {
            "id": item.id,
            "headline": item.headline,
            "tag": item.tag,
            "photoUrl": item.photo_url or None,
            "age": get_relative_time(item.publish_date),
            "href": item.url,
        }
        for item in qs
    ]
