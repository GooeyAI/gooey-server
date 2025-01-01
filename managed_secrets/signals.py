from django.db.models.signals import post_delete
from django.dispatch import receiver

from managed_secrets.models import ManagedSecret


@receiver(post_delete, sender=ManagedSecret)
def on_secret_deleted(instance: ManagedSecret, **kwargs):
    instance.delete_value()
