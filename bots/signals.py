from django.db.models.signals import post_save
from django.dispatch import receiver

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
        # msg_analysis.delay(msg_id=instance.id)
        for anal in analysis_runs:
            msg_analysis.delay(msg_id=instance.id, sr_id=anal.get_active_saved_run().id)
        instance._analysis_started = True
