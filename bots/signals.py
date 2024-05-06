from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from bots.models import Message, CHATML_ROLE_ASSISSTANT
from bots.tasks import msg_analysis


@receiver(post_save, sender=Message)
def run_after_message_save(instance: Message, **kwargs):
    analysis_runs = instance.conversation.bot_integration.analysis_runs.all()
    if (
        # analysis is enabled
        analysis_runs.exists()
        # analysis is not running
        and not instance._analysis_started
        # this is the assistant's response
        and instance.role == CHATML_ROLE_ASSISSTANT
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
