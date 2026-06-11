from __future__ import annotations

import mimetypes
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Literal

import gooey_gui as gui
from django.db.models import Count, OuterRef, Prefetch, Q, Subquery
from django.utils import timezone
from furl import furl
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from starlette.requests import Request

from app_users.models import AppUser
from bots.models import PublishedRun, PublishedRunVersion, SavedRun, Workflow
from bots.models.published_run import Tag
from bots.models.workflow import WorkflowAccessLevel, WorkflowMetadata
from cms.models import NewsItem, WorkflowCard, WorkflowTab
from daras_ai.image_input import truncate_text_words
from daras_ai_v2.meta_content import raw_build_meta_tags
from daras_ai_v2.preview_img import media_preview_img
from daras_ai_v2.utils import get_relative_time
from widgets.workflow_search import get_filter_value_from_workspace
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


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class ChatPreview(CamelModel):
    type: Literal["chat"] = "chat"
    user_message: str | None = None
    bot_message: str | None = None


class MediaPreview(CamelModel):
    type: Literal["image", "video", "audio"]
    url: str
    preview_img: str | None = None
    caption: str | None = None


class IconPreview(CamelModel):
    type: Literal["icon"] = "icon"
    image_url: str | None = None
    icon: str | None = None


CardPreview = Annotated[
    ChatPreview | MediaPreview | IconPreview, Field(discriminator="type")
]


class AccessBadgeData(CamelModel):
    icon_html: str
    label: str


class WorkflowCardData(CamelModel):
    title: str
    href: str
    workflow_icon: str | None = None
    description: str | None = None
    author_name: str | None = None
    author_photo_url: str | None = None
    preview: CardPreview | None = None
    updated_at: str | None = None
    run_count: int | None = None
    access_badge: AccessBadgeData | None = None
    change_notes: str | None = None


class WorkflowTabData(CamelModel):
    id: int
    title: str
    icon: str
    cards: list[WorkflowCardData]


class WorkspaceHeaderData(CamelModel):
    name: str
    photo_url: str
    description: str | None = None
    settings_href: str | None = None


class IndustryTileData(CamelModel):
    id: int
    name: str
    icon: str
    color: str | None = None
    description: str
    workflow_count: int
    href: str


class NewsItemData(CamelModel):
    id: int
    headline: str
    tag: str
    photo_url: str | None = None
    publish_date: str
    href: str


def render(request: Request):
    is_anonymous = request.user is None or request.user.is_anonymous
    workspace = (
        get_current_workspace(request.user, request.session)
        if not is_anonymous
        else None
    )
    workspace_header = _get_workspace_header(request.user, workspace)
    metadata_by_workflow: MetadataByWorkflow = {}
    if not is_anonymous and workspace_header is None:
        greeting = _get_greeting(request.user)
    else:
        greeting = None

    gui.component(
        "HomePage",
        greeting=greeting,
        workspaceHeader=workspace_header,
        recentWorkflows=_load_recent_workflows(
            request.user, workspace, metadata_by_workflow
        ),
        savedWorkflows=_load_saved_workflows(
            request.user, workspace, metadata_by_workflow
        ),
        savedWorkflowsHref=_saved_workflows_href(workspace),
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
        .select_related("workflow_metadata")
        .prefetch_related(
            Prefetch(
                "cards",
                queryset=WorkflowCard.objects.filter(priority__gte=1)
                .select_related(
                    "workflow__workspace__created_by",
                    "workflow__saved_run",
                )
                .order_by("-priority"),
            )
        )
        .order_by("-priority")
    )
    tabs = []
    for tab in qs:
        metadata = _get_workflow_metadata(
            Workflow(tab.workflow_metadata.workflow),
            metadata_by_workflow,
            prefetched=tab.workflow_metadata,
        )
        tabs.append(
            WorkflowTabData(
                id=tab.id,
                title=metadata.short_title if metadata else "",
                icon=metadata.tab_icon_html() if metadata else "",
                cards=[
                    pr_to_json(
                        card.workflow,
                        author=author_from_workspace(card.workflow.workspace),
                        metadata_by_workflow=metadata_by_workflow,
                    )
                    for card in tab.cards.all()
                ],
            )
        )
    return tabs


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
        data.updated_at = get_relative_time(sr.updated_at)
    return data


def _saved_card(
    pr: PublishedRun,
    *,
    author: AuthorData | None,
    metadata_by_workflow: MetadataByWorkflow,
) -> WorkflowCardData:
    data = pr_to_json(pr, author=author, metadata_by_workflow=metadata_by_workflow)
    if pr.updated_at:
        data.updated_at = get_relative_time(pr.updated_at)
    if pr.run_count:
        data.run_count = pr.run_count
    data.access_badge = AccessBadgeData.model_validate(pr.get_share_badge_data())
    change_notes = getattr(pr, "latest_change_notes", None)
    if change_notes:
        data.change_notes = change_notes
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
    return WorkflowCardData(
        title=(parent_pr and parent_pr.title) or workflow.label,
        href=sr.get_app_url(),
        workflow_icon=(metadata and (metadata.fa_icon or metadata.emoji)) or "",
        description=(parent_pr and parent_pr.notes) or None,
        preview=_sr_preview(workflow=workflow, sr=sr, pr=parent_pr, metadata=metadata),
        **_author_fields(author),
    )


def pr_to_json(
    pr: PublishedRun,
    *,
    author: AuthorData | None,
    metadata_by_workflow: MetadataByWorkflow,
) -> WorkflowCardData:
    workflow = Workflow(pr.workflow)
    metadata = _get_workflow_metadata(workflow, metadata_by_workflow)
    return WorkflowCardData(
        title=pr.title or workflow.label,
        href=pr.get_app_url(),
        description=pr.notes or None,
        preview=_pr_preview(pr, workflow=workflow, metadata=metadata),
        **_author_fields(author),
    )


def _author_fields(author: AuthorData | None) -> dict:
    if author is None:
        return {}
    return {"author_name": author.name, "author_photo_url": author.photo_url}


def _get_workflow_metadata(
    workflow: Workflow,
    cache: MetadataByWorkflow,
    *,
    prefetched: WorkflowMetadata | None = None,
) -> WorkflowMetadata | None:
    if workflow not in cache:
        cache[workflow] = prefetched or workflow.get_metadata()
    return cache[workflow]


def _sr_preview(
    *,
    workflow: Workflow,
    sr: SavedRun,
    pr: PublishedRun | None,
    metadata: WorkflowMetadata | None,
) -> CardPreview | None:
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
) -> CardPreview | None:
    if pr.photo_url:
        return _media_preview(output_url=pr.photo_url, caption=None)

    page_cls: type[BasePage] = workflow.page_cls
    state = pr.saved_run.state if pr.saved_run_id else {}
    output_url = page_cls.preview_output(state) if state else None
    if output_url:
        return _media_preview(output_url=output_url, state=state, page_cls=page_cls)

    return _icon_preview(metadata)


def _icon_preview(metadata: WorkflowMetadata | None) -> IconPreview | None:
    if not metadata or not (
        metadata.default_image or metadata.fa_icon or metadata.emoji
    ):
        return None
    return IconPreview(
        image_url=metadata.default_image or None,
        icon=metadata.fa_icon or metadata.emoji or None,
    )


def _chat_preview(state: dict) -> ChatPreview | None:
    user_message = state.get("input_prompt") or state.get("raw_input_text")
    output_text = state.get("output_text") or []
    bot_message = output_text[0] if output_text else None
    if not user_message and not bot_message:
        return None
    return ChatPreview(
        user_message=_preview_text(user_message, CHAT_PREVIEW_MAXLEN),
        bot_message=_preview_text(bot_message, CHAT_PREVIEW_MAXLEN),
    )


def _media_preview(
    *,
    output_url: str,
    state: dict | None = None,
    page_cls: type[BasePage] | None = None,
    caption: str | None = None,
) -> MediaPreview:
    if caption is None and page_cls is not None and state is not None:
        caption = _preview_text(page_cls.preview_input(state), MEDIA_CAPTION_MAXLEN)
    content_type = mimetypes.guess_type(output_url)[0] or ""
    if content_type.startswith("video/"):
        media_type = "video"
    elif content_type.startswith("audio/"):
        media_type = "audio"
    else:
        media_type = "image"
    return MediaPreview(
        type=media_type,
        url=output_url,
        preview_img=media_preview_img(output_url),
        caption=caption,
    )


def _preview_text(text: str | None, maxlen: int) -> str | None:
    if not text:
        return None
    return truncate_text_words(text, maxlen=maxlen).replace("\n", " ")


def _load_industry_tiles() -> list[IndustryTileData]:
    qs = (
        Tag.objects.filter(featured=True, hide=False)
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
