from __future__ import annotations

import mimetypes
import threading
import typing
from contextlib import contextmanager
from datetime import datetime
from typing import TYPE_CHECKING


import gooey_gui as gui
from django.db.models import Count, OuterRef, Q, Subquery, F
from django.utils import timezone
from furl import furl
from starlette.requests import Request

from app_users.models import AppUser
from bots.models import PublishedRun, PublishedRunVersion, SavedRun, Workflow
from bots.models.published_run import Tag
from bots.models.workflow import WorkflowAccessLevel, WorkflowMetadata
from cms.models import NewsItem
from daras_ai.image_input import truncate_text_words
from daras_ai_v2.meta_content import raw_build_meta_tags
from daras_ai_v2.preview_img import media_preview_img
from daras_ai_v2.utils import get_relative_time
from gooey_gui.types.home_page_props import (
    CardPreview,
    ChatPreview,
    IconPreview,
    IndustryTileData,
    MediaPreview,
    NewsItemData,
    WorkflowCardData,
    WorkflowTabData,
    WorkspaceHeaderData,
    HomePageProps,
    AuthorData,
)
from widgets.workflow_search import get_filter_value_from_workspace
from workspaces.models import Workspace
from workspaces.widgets import get_current_workspace

if TYPE_CHECKING:
    from daras_ai_v2.base import BasePage

META_TITLE = "Home | Gooey.AI"
META_DESCRIPTION = "Build AI workflows on Gooey.AI"

WORKFLOW_LIST_LIMIT = 3
RECENT_WORKFLOW_LIST_LIMIT = 4
RECENT_WORKFLOW_SCAN_LIMIT = 200
NEWS_ITEM_LIST_LIMIT = 4

CHAT_PREVIEW_MAXLEN = 130
MEDIA_CAPTION_MAXLEN = 60


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

    with get_featured_workflows() as featured_workflows:
        gui.model_component(
            HomePageProps(
                greeting=greeting,
                workspace_header=workspace_header,
                workflow_tabs=list(_load_workflow_tabs(featured_workflows)),
                recent_workflows=_load_recent_workflows(request.user, workspace),
                saved_workflows=_load_saved_workflows(request.user, workspace),
                saved_workflows_href=_saved_workflows_href(workspace),
                industry_tiles=_load_industry_tiles(),
                news_items=_load_news_items(),
            ),
        )


@contextmanager
def get_featured_workflows() -> typing.Iterator[list[Workflow | int]]:
    qs = WorkflowMetadata.objects.filter(is_featured=True).order_by("-priority")
    cache = workflow_metadata_cache()
    try:
        for metadata in qs:
            cache[metadata.workflow] = metadata
        yield [metadata.workflow for metadata in qs]
    finally:
        cache.clear()


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
        if len(ids) >= RECENT_WORKFLOW_LIST_LIMIT:
            break

    return [
        _history_card(sr, author=author_from_user(user, current_user=user))
        for sr in SavedRun.objects.filter(id__in=ids).order_by("-updated_at")
    ]


def _load_saved_workflows(
    user: AppUser | None,
    workspace: Workspace | None,
) -> list[WorkflowCardData]:
    return [
        _saved_card(pr, author=author_from_user(pr.last_edited_by, current_user=user))
        for pr in saved_published_runs(user, workspace)
    ]


def saved_published_runs(
    user: AppUser | None,
    workspace: Workspace | None,
    limit: int = WORKFLOW_LIST_LIMIT,
) -> list[PublishedRun]:
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
    return list(
        PublishedRun.objects.filter(pr_filter)
        .select_related("last_edited_by", "saved_run", "workspace")
        .annotate(latest_change_notes=Subquery(latest_change_notes))
        .order_by("-updated_at")[:limit]
    )


def _load_workflow_tabs(
    featured_workflows: list[Workflow | int],
) -> typing.Iterable[WorkflowTabData]:
    pr_qs = (
        PublishedRun.objects.select_related("workspace__created_by", "saved_run")
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
        metadata = get_workflow_metadata(workflow)
        yield WorkflowTabData(
            id=metadata.workflow,
            title=metadata.short_title,
            icon=metadata.tab_icon_html(),
            cards=[
                pr_to_card(pr, author=author_from_workspace(pr.workspace))
                for pr in pr_group
            ],
        )


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
) -> WorkflowCardData:
    data = sr_to_card(sr, author=author)
    if sr.updated_at:
        data.updated_at = get_relative_time(sr.updated_at)
    return data


def _saved_card(
    pr: PublishedRun,
    *,
    author: AuthorData | None,
) -> WorkflowCardData:
    data = pr_to_card(pr, author=author)
    if pr.updated_at:
        data.updated_at = get_relative_time(pr.updated_at)
    if pr.run_count:
        data.run_count = pr.run_count
    data.access_badge = pr.get_access_badge_data()
    change_notes = getattr(pr, "latest_change_notes", None)
    if change_notes:
        data.change_notes = change_notes
    return data


def sr_to_card(
    sr: SavedRun,
    *,
    author: AuthorData | None,
) -> WorkflowCardData:
    parent_pr = sr.parent_published_run()
    workflow = Workflow(sr.workflow)
    metadata = get_workflow_metadata(workflow)
    return WorkflowCardData(
        title=(parent_pr and parent_pr.title) or workflow.label,
        href=sr.get_app_url(),
        workflow_icon=(metadata and (metadata.fa_icon or metadata.emoji)) or "",
        description=(parent_pr and parent_pr.notes) or None,
        preview=_sr_preview(workflow=workflow, sr=sr, pr=parent_pr, metadata=metadata),
        author=author,
    )


def pr_to_card(
    pr: PublishedRun,
    *,
    author: AuthorData | None,
) -> WorkflowCardData:
    workflow = Workflow(pr.workflow)
    metadata = get_workflow_metadata(workflow)
    return WorkflowCardData(
        title=pr.title or workflow.label,
        href=pr.get_app_url(),
        description=pr.notes or None,
        preview=_pr_preview(pr, workflow=workflow, metadata=metadata),
        author=author,
    )


def get_workflow_metadata(workflow: Workflow | int) -> WorkflowMetadata:
    cache = workflow_metadata_cache()
    try:
        metadata = cache[workflow]
    except KeyError:
        metadata = cache[workflow] = Workflow(workflow).get_or_create_metadata()
    return metadata


def workflow_metadata_cache() -> dict[int, WorkflowMetadata]:
    return threadlocal.__dict__.setdefault("workflow_metadata_cache", {})


threadlocal = threading.local()


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
