from django.db import transaction
from django.db.models import Q
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from loguru import logger

from bots.models import Message, SavedRun, Workflow
from bots.models.run_conversation import RunConversation
from bots.tasks import msg_analysis
from daras_ai_v2.base import STARTING_STATE
from daras_ai_v2.language_model import CHATML_ROLE_ASSISTANT
from django.db import IntegrityError


@receiver(pre_save, sender=SavedRun)
def save_saved_run_cancelled_transition(instance: SavedRun, **kwargs):
    if not (instance.pk and instance.is_cancelled):
        instance._just_cancelled = False
        return
    try:
        saved_run = SavedRun.objects.get(pk=instance.pk)
    except SavedRun.DoesNotExist:
        instance._just_cancelled = False
    else:
        instance._just_cancelled = not saved_run.is_cancelled


@receiver(post_save, sender=SavedRun)
def revoke_saved_run_task_on_cancel(instance: SavedRun, **kwargs):
    if not getattr(instance, "_just_cancelled", False):
        return

    if instance.run_status == STARTING_STATE:
        # just in case the celery task never started
        instance.run_status = ""
        instance.save(update_fields=["run_status"])

    task_id = instance.celery_task_id
    if not task_id:
        return

    @transaction.on_commit
    def _():
        try:
            from celeryapp.celeryconfig import app

            app.control.revoke(task_id, terminate=True, signal="SIGUSR1")
        except Exception as e:
            logger.warning(f"failed to revoke celery task {task_id}: {e}")


@receiver(post_save, sender=SavedRun)
def create_run_conversation(instance: SavedRun, **kwargs):
    sr = instance
    if (
        sr.workflow != Workflow.VIDEO_BOTS
        or "messages" not in sr.state
        or sr.surface == SavedRun.Surface.deployment
    ):
        return
    try:
        if sr.run_conversation:
            return
    except RunConversation.DoesNotExist:
        pass

    parent = sr.parent

    if (
        parent
        and parent.workspace_id == sr.workspace_id
        and is_continued_conversation(sr, parent)
    ):
        try:
            parent_convo = parent.run_conversation
            with transaction.atomic():
                parent_convo.last_msg = sr
                parent_convo.save(update_fields=["last_msg"])
                parent_convo.messages.add(sr)
                return
        except (RunConversation.DoesNotExist, IntegrityError):
            pass

    with transaction.atomic():
        run_convo = RunConversation.objects.create(
            first_msg=sr,
            last_msg=sr,
            title=sr.state.get("input_prompt") or "",
        )
        run_convo.messages.add(sr)


@receiver(post_save, sender=Message)
def create_run_conversation_for_deployment(instance: Message, **kwargs):
    sr = instance.saved_run
    if instance.role != CHATML_ROLE_ASSISTANT or not sr:
        return
    try:
        if sr.run_conversation:
            return
    except RunConversation.DoesNotExist:
        pass
    convo = instance.conversation
    try:
        run_convo = convo.run_conversation
    except RunConversation.DoesNotExist:
        try:
            first_msg = convo.messages.earliest().saved_run
        except Message.DoesNotExist:
            first_msg = sr
        try:
            with transaction.atomic():
                run_convo = RunConversation.objects.create(
                    first_msg=first_msg,
                    last_msg=sr,
                    title=sr.state.get("input_prompt") or "",
                    bot_conversation=convo,
                )
                run_convo.messages.add(
                    *convo.messages.filter(saved_run__isnull=False).values_list(
                        "saved_run", flat=True
                    )
                )
                return
        except IntegrityError:
            run_convo = RunConversation.objects.get(
                Q(bot_conversation=convo) | Q(last_msg=sr)
            )
    run_convo.last_msg = sr
    run_convo.save(update_fields=["last_msg"])
    run_convo.messages.add(sr)


def is_continued_conversation(sr: SavedRun, parent: SavedRun) -> bool:
    messages = sr.state.get("messages")
    if not messages:
        return False
    for msg in reversed(messages):
        uid = msg.get("uid")
        run_id = msg.get("run_id")
        if not (uid and run_id):
            continue
        return uid == parent.uid and run_id == parent.run_id
    return False


@receiver(post_save, sender=Message)
def run_after_message_save(instance: Message, **kwargs):
    analysis_runs = instance.conversation.bot_integration.analysis_runs.all()
    if (
        # analysis is enabled
        analysis_runs.exists()
        # analysis is not running
        and not instance._analysis_started
        # this is the assistant's response
        and instance.role == CHATML_ROLE_ASSISTANT
        # msg is acutally produced by a copilot run
        and instance.saved_run
    ):

        @transaction.on_commit
        def _():
            for anal in analysis_runs:
                countdown = None
                if anal.last_run_at and anal.cooldown_period:
                    countdown = (
                        anal.cooldown_period - (timezone.now() - anal.last_run_at)
                    ).total_seconds()
                    if countdown < 0:
                        countdown = None

                result = msg_analysis.apply_async(
                    args=(),
                    kwargs=dict(
                        msg_id=instance.id, anal_id=anal.id, countdown=countdown
                    ),
                    countdown=countdown,
                )

                if countdown:
                    anal.scheduled_task_id = result.id
                anal.save(update_fields=["scheduled_task_id"])

        instance._analysis_started = True
