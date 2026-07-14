from __future__ import annotations

import mimetypes
from typing import TYPE_CHECKING

from app_users.models import AppUser
from bots.models import PublishedRun, SavedRun, Workflow
from bots.models.workflow import WorkflowMetadata
from daras_ai.image_input import truncate_text_words
from daras_ai_v2.preview_img import media_preview_img
from daras_ai_v2.utils import get_relative_time
from gooey_gui.types.home_page_props import (
    AuthorData,
    CardPreview,
    ChatPreview,
    IconPreview,
    MediaPreview,
    WorkflowCardData,
)
from workspaces.models import Workspace

if TYPE_CHECKING:
    from daras_ai_v2.base import BasePage

CHAT_PREVIEW_MAXLEN = 130
MEDIA_CAPTION_MAXLEN = 60


def author_from_user(
    user: AppUser | None, current_user: AppUser | None
) -> AuthorData | None:
    if user is None:
        return None
    if current_user is not None and user.uid == current_user.uid:
        return AuthorData(name="You", photo_url=user.get_photo())
    return AuthorData(name=user.full_name(), photo_url=user.get_photo())


def author_from_workspace(workspace: Workspace) -> AuthorData:
    return AuthorData(
        name=workspace.display_name(),
        photo_url=workspace.get_photo() or None,
    )


def history_card(
    sr: SavedRun,
    *,
    author: AuthorData | None,
) -> WorkflowCardData:
    data = sr_to_card(sr, author=author)
    if sr.updated_at:
        data.updated_at = get_relative_time(sr.updated_at)
    return data


def saved_card(
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
    metadata = sr.get_workflow_metadata()
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
    metadata = pr.get_workflow_metadata()
    return WorkflowCardData(
        title=pr.title or workflow.label,
        href=pr.get_app_url(),
        description=pr.notes or None,
        preview=_pr_preview(pr, workflow=workflow, metadata=metadata),
        author=author,
    )


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
