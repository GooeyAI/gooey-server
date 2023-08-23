from django.db.models.signals import post_save
from django.dispatch import receiver

from bots.models import Message, CHATML_ROLE_ASSISSTANT
from bots.tasks import msg_analysis


# Receiver for Message Signal
@receiver(post_save, sender=Message)
def run_after_message_save(instance: Message, **kwargs):
    if (
        # analysis is enabled
        instance.conversation.bot_integration.analysis_run
        # analysis is not running
        and not instance._analysis_started
        # this is the assistant's response
        and instance.role == CHATML_ROLE_ASSISSTANT
    ):
        msg_analysis.delay(msg_id=instance.id)
        instance._analysis_started = True
