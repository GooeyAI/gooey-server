from __future__ import annotations

import datetime
import mimetypes
from typing import TYPE_CHECKING

from django.utils import timezone

from app_users.models import AppUser
from bots.models import Conversation, PublishedRun, SavedRun, Workflow
from bots.models.bot_integration import Platform
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
    RunStatusData,
    SenderData,
    WorkflowCardData,
)
from workspaces.models import Workspace

if TYPE_CHECKING:
    from daras_ai_v2.base import BasePage

CHAT_PREVIEW_MAXLEN = 130
MEDIA_CAPTION_MAXLEN = 60

# Nothing kills a celery worker on a clock, so a run whose status stopped moving
# is indistinguishable from one still working. Past this, the card stops claiming
# it's running - a permanent spinner on a dead run is worse than calling it early.
RUN_STALE_AFTER = datetime.timedelta(minutes=10)

# the badge shares the preview's top edge with the workflow icon, so a long
# status line gets cut here rather than growing across it
RUN_STATUS_MAXLEN = 28

# `BasePage.STARTING_STATE`, normalised the way that page compares it. Copied
# rather than imported: base_v2 imports this module.
STARTING_STATE = "starting"

# An id is masked to first-3 + last-4. Anything shorter would leak most of
# itself to the mask, so it's shown whole instead - a display name like @seanb
# is meant to be read anyway.
MASK_MIN_LEN = len("123") + len("1233") + 1


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
    sender = sender_from_run(sr)
    return WorkflowCardData(
        title=_run_title(sr, (parent_pr and parent_pr.title) or workflow.label),
        href=sr.get_app_url(),
        workflow_icon=(metadata and (metadata.fa_icon or metadata.emoji)) or "",
        description=(parent_pr and parent_pr.notes) or None,
        preview=_sr_preview(workflow=workflow, sr=sr, pr=parent_pr, metadata=metadata),
        # whoever owns the integration didn't send the message, so the sender
        # takes the author's place rather than sitting next to it
        author=None if sender else author,
        sender=sender,
        run_status=run_status_from_run(sr),
    )


def _run_title(sr: SavedRun, title: str) -> str:
    """Name the surface a run came from, so a deployment doesn't read like a playground run."""
    try:
        surface = SavedRun.Surface(sr.surface)
    except ValueError:
        return title
    return f"{surface.label}: {title}"


def run_status_from_run(sr: SavedRun) -> RunStatusData | None:
    """What this run is doing, when that's still worth saying.

    Mirrors `BasePage.get_run_state`, off the model's own columns rather than the
    state blob, plus the two things that page can't see from a single run: a
    cancel, and a worker that stopped reporting.
    """
    if sr.is_cancelled:
        return RunStatusData(state="cancelled", label="Cancelled")
    if sr.error_msg:
        return RunStatusData(state="failed", label="Failed")
    if not sr.run_status:
        # completed, or never started - neither needs a badge
        return None
    if sr.updated_at and timezone.now() - sr.updated_at > RUN_STALE_AFTER:
        return RunStatusData(state="failed", label="Timed out")
    if sr.run_status.lower().strip(". ") == STARTING_STATE:
        return RunStatusData(state="starting", label="Starting")
    return RunStatusData(
        state="running",
        label=truncate_text_words(sr.run_status, maxlen=RUN_STATUS_MAXLEN),
    )


def sender_from_run(sr: SavedRun) -> SenderData | None:
    """Who this run was for, when it came in over a bot integration.

    Needs `message_thread__bot_conversation` selected to stay off the N+1 path.
    """
    if sr.platform is None:
        return None
    try:
        platform = Platform(sr.platform)
    except ValueError:
        # a run recorded on a platform this deploy doesn't know about - the card
        # is worth rendering without its origin, a 500 isn't
        return None
    convo = sr.message_thread and sr.message_thread.bot_conversation
    return SenderData(
        icon=platform.get_icon(),
        # a run can carry a platform without a conversation behind it (an older
        # run, or a thread since deleted) - the icon alone still says where it
        # came from, so fall back to that rather than dropping the row's origin
        label=_sender_label(platform, convo) if convo else "",
        title=platform.get_title(),
    )


def _sender_label(platform: Platform, convo: Conversation) -> str:
    match platform:
        case Platform.WHATSAPP if convo.wa_phone_number:
            return mask_user_id(convo.wa_phone_number.as_international)
        case Platform.TWILIO if convo.twilio_phone_number:
            return mask_user_id(convo.twilio_phone_number.as_international)
        case Platform.SLACK if convo.slack_user_name:
            return "@" + mask_user_id(convo.slack_user_name)
        case Platform.INSTAGRAM if convo.ig_username:
            return "@" + mask_user_id(convo.ig_username)
        case Platform.FACEBOOK if convo.fb_page_name:
            return "@" + mask_user_id(convo.fb_page_name)
        case Platform.TELEGRAM if convo.telegram_user_name:
            return "@" + mask_user_id(convo.telegram_user_name)
    return mask_user_id(convo.unique_user_id() or "")


def mask_user_id(value: str) -> str:
    """Keep enough of an id to recognise a returning sender, not enough to reach them."""
    value = value.strip()
    if len(value) < MASK_MIN_LEN:
        return value
    return f"{value[:3]}xxx{value[-4:]}"


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
