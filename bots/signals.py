from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from loguru import logger

from bots.models import Message, SavedRun
from bots.tasks import msg_analysis
from daras_ai_v2.base import STARTING_STATE
from daras_ai_v2.language_model import CHATML_ROLE_ASSISTANT


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
