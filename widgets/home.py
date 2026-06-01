import mimetypes
from datetime import date
from typing import Literal, TypedDict

import gooey_gui as gui
from django.db.models import Count, OuterRef, Prefetch, Q, Subquery
from furl import furl
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

WorkflowCardProfile = Literal["history", "saved", "picker"]

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
    workflowLabel: str
    workflowEmoji: str
    description: str
    authorName: str
    authorPhotoUrl: str | None
    preview: dict
    updatedAt: str
    runCount: int
    accessBadge: AccessBadgeData


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
    gui.component(
        "HomePage",
        greeting=(
            _get_greeting(request.user)
            if not is_anonymous and workspace_header is None
            else None
        ),
        workspaceHeader=workspace_header,
        recentWorkflows=_load_recent_workflows(request.user, workspace),
        savedWorkflows=_load_saved_workflows(request.user, workspace),
        workflowTabs=_load_workflow_tabs(),
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
    user: AppUser | None, workspace: Workspace | None
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
        _workflow_to_json(
            profile="history",
            sr=sr,
            author=_history_author(sr, user=user, authors_by_uid=authors_by_uid),
            current_user=user,
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
    user: AppUser | None, workspace: Workspace | None
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
        _workflow_to_json(
            profile="saved",
            pr=pr,
            author=pr.last_edited_by,
            current_user=user,
        )
        for pr in prs
    ]


def _load_workflow_tabs() -> list[WorkflowTabData]:
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
                _workflow_to_json(
                    profile="picker",
                    pr=card.recipe,
                    author=card.recipe.workspace,
                )
                for card in tab.cards.all()
            ],
        }
        for tab in qs
    ]


def _workflow_to_json(
    *,
    profile: WorkflowCardProfile,
    pr: PublishedRun | None = None,
    sr: SavedRun | None = None,
    author: AppUser | Workspace | None = None,
    current_user: AppUser | None = None,
) -> WorkflowCardData:
    if profile == "history":
        if sr is None:
            raise ValueError("history profile requires sr")
        parent_pr = pr or sr.parent_published_run()
        workflow = Workflow(sr.workflow)
        title = (parent_pr and parent_pr.title) or workflow.label
        href = sr.get_app_url()
        updated_at = sr.updated_at
        metadata = workflow.get_metadata()
        preview = _sr_preview(
            workflow=workflow,
            sr=sr,
            pr=parent_pr,
            metadata=metadata,
            include_chat=True,
        )
        notes = parent_pr and parent_pr.notes
    elif profile in ("saved", "picker"):
        if pr is None:
            raise ValueError(f"{profile} profile requires pr")
        workflow = Workflow(pr.workflow)
        title = pr.title or workflow.label
        href = pr.get_app_url()
        updated_at = pr.updated_at
        metadata = workflow.get_metadata()
        preview = _pr_preview(pr, workflow=workflow, metadata=metadata)
        notes = pr.notes

    data: WorkflowCardData = {"title": title, "href": href}

    if profile == "history":
        data["workflowLabel"] = workflow.label
        data["workflowEmoji"] = (metadata.emoji if metadata else "") or ""

    if isinstance(author, Workspace):
        data["authorName"] = author.display_name()
        data["authorPhotoUrl"] = author.get_photo() or None
    elif isinstance(author, AppUser):
        if current_user is not None and author.uid == current_user.uid:
            data["authorName"] = "You"
            data["authorPhotoUrl"] = current_user.photo_url or None
        else:
            data["authorName"] = author.display_name or ""
            data["authorPhotoUrl"] = author.photo_url or None

    if notes:
        data["description"] = notes
    if preview is not None:
        data["preview"] = preview
    if updated_at and profile != "picker":
        data["updatedAt"] = get_relative_time(updated_at)

    if profile == "saved":
        if pr.run_count:
            data["runCount"] = pr.run_count
        data["accessBadge"] = pr.get_share_badge_data()
        change_notes = getattr(pr, "latest_change_notes", None)
        if change_notes:
            data["changeNotes"] = change_notes

    return data


def _sr_preview(
    *,
    workflow: Workflow,
    sr: SavedRun,
    pr: PublishedRun | None,
    metadata: WorkflowMetadata | None,
    include_chat: bool,
) -> dict | None:
    state = sr.state

    if include_chat and workflow == Workflow.VIDEO_BOTS:
        chat = _chat_preview(state)
        if chat:
            return chat

    page_cls = workflow.page_cls
    output_url = page_cls.preview_output(state) or (pr and pr.photo_url) or None
    if output_url:
        return _media_preview(output_url=output_url, state=state, page_cls=page_cls)

    return _icon_preview(workflow, metadata=metadata)


def _pr_preview(
    pr: PublishedRun,
    *,
    workflow: Workflow,
    metadata: WorkflowMetadata | None,
) -> dict | None:
    if pr.photo_url:
        return _media_preview(output_url=pr.photo_url, caption=None)

    page_cls = workflow.page_cls
    state = pr.saved_run.state if pr.saved_run_id else {}
    output_url = page_cls.preview_output(state) if state else None
    if output_url:
        return _media_preview(output_url=output_url, state=state, page_cls=page_cls)

    return _icon_preview(workflow, metadata=metadata)


def _icon_preview(
    workflow: Workflow, *, metadata: WorkflowMetadata | None
) -> dict | None:
    metadata = metadata or workflow.get_metadata()
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
    page_cls=None,
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
    qs = NewsItem.objects.filter(publish_date__lte=date.today()).order_by(
        "-publish_date"
    )[:NEWS_ITEM_LIST_LIMIT]
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
