from datetime import timedelta

from django.contrib.humanize.templatetags.humanize import naturaltime
from django.utils import timezone
from starlette.exceptions import HTTPException

from app_users.models import AppUser
from bots.models import Workflow, SavedRun
from bots.models.convo_msg import (
    CHATML_ROLE_USER,
    ConvoBlockedStatus,
    Conversation,
    Message,
)
from daras_ai_v2 import settings
from workspaces.models import Workspace


def ensure_bot_rate_limits(convo: Conversation):
    if convo.bot_integration.disable_rate_limits:
        return

    msgs_today = Message.objects.filter(
        role=CHATML_ROLE_USER,
        created_at__gte=timezone.now() - timedelta(days=1),
        conversation__bot_integration=convo.bot_integration,
        **{
            f"conversation__{field}": getattr(convo, field)
            for field in Conversation.user_id_fields
        },
    )
    num_msgs = msgs_today.count()

    if num_msgs > settings.MAX_MESSAGES_PER_DAY_BLOCK:
        # block the conversation
        if convo.blocked_status != ConvoBlockedStatus.BLOCKED:
            convo.blocked_status = ConvoBlockedStatus.BLOCKED
            convo.blocked_at = timezone.now()
            convo.save(update_fields=["blocked_status", "blocked_at"])
        raise RateLimitExceeded(
            retry_after=0,
            msg="You have been blocked from using this bot.",
        )

    if num_msgs > settings.MAX_MESSAGES_PER_DAY_WARNING:
        if convo.blocked_status != ConvoBlockedStatus.WARNING:
            convo.blocked_status = ConvoBlockedStatus.WARNING
            convo.blocked_at = timezone.now()
            convo.save(update_fields=["blocked_status", "blocked_at"])
        retry_after = timedelta(hours=25) - (
            timezone.now() - msgs_today.latest("created_at").created_at
        )
        raise RateLimitExceeded(
            retry_after=retry_after.total_seconds(),
            msg=(
                "You've reached your daily message limit for today. "
                f"Please try again after {naturaltime(timezone.now() + retry_after)}. "
            ),
        )

    if convo.blocked_status != ConvoBlockedStatus.NORMAL:
        convo.blocked_status = ConvoBlockedStatus.NORMAL
        convo.blocked_at = None
        convo.save(update_fields=["blocked_status", "blocked_at"])


def ensure_rate_limits(
    workflow: Workflow,
    user: AppUser,
    workspace: Workspace,
    *,
    max_requests: int = None,
    max_requests_reset_min: float = None,
    max_concurrency: int = None,
    max_concurrency_reset_min: int = None,
    estimated_run_time_sec: float = 2 * 60,
):
    if user.disable_rate_limits:
        return

    if max_requests is None:
        if user.is_anonymous:
            max_requests = settings.MAX_RPM_ANON
        elif workspace.is_paying:
            max_requests = settings.MAX_RPM_PAID
        else:
            max_requests = settings.MAX_RPM_FREE
        max_requests_reset_min = 1

    if max_concurrency is None:
        if user.is_anonymous:
            max_concurrency = settings.MAX_CONCURRENCY_ANON
        elif workspace.is_paying:
            max_concurrency = settings.MAX_CONCURRENCY_PAID
        else:
            max_concurrency = settings.MAX_CONCURRENCY_FREE
        max_concurrency_reset_min = 30

    qs = SavedRun.objects.filter(workflow=workflow, uid=user.uid)
    requests = qs.filter(
        created_at__gte=timezone.now() - timedelta(minutes=max_requests_reset_min)
    ).count()
    if requests >= max_requests:
        short_title = workflow.get_or_create_metadata().short_title
        retry_after = (
            timedelta(minutes=max_requests_reset_min)
            - (timezone.now() - qs.latest("created_at").created_at)
        ).total_seconds()
        raise RateLimitExceeded(
            retry_after,
            f"Rate limit reached for {short_title} requests.\n\n "
            f"Limit: {max_requests} requests in {max_requests_reset_min}m.\n "
            f"Used: {requests} requests.\n "
            f"Retry after: {retry_after:.1f}s.",
        )

    running = (
        qs.filter(
            created_at__gte=timezone.now()
            - timedelta(minutes=max_concurrency_reset_min)
        )
        .exclude(run_status="")
        .count()
    )
    if running >= max_concurrency:
        short_title = workflow.get_or_create_metadata().short_title
        retry_after = (running - max_concurrency + 1) * estimated_run_time_sec
        raise RateLimitExceeded(
            retry_after,
            f"Rate limit reached for {short_title} concurrency.\n\n "
            f"Limit: {max_concurrency} concurrent runs in {max_concurrency_reset_min}m.\n "
            f"Used: {running} runs.\n "
            f"Retry after (approx) {retry_after}s, or wait for running jobs to finish.",
        )


class RateLimitExceeded(HTTPException):
    def __init__(self, retry_after: float, msg: str):
        self.status_code = 429
        self.headers = {
            "Retry-After": str(retry_after),
        }
        self.detail = dict(error=msg)

    def __repr__(self):
        pass
