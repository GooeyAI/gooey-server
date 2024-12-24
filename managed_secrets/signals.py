from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from managed_secrets.models import ManagedSecret


@receiver(post_save, sender=ManagedSecret)
def on_secret_saved(instance: ManagedSecret, **kwargs):
    if instance.value is None:
        return
    instance.store_value(instance.value)


@receiver(post_delete, sender=ManagedSecret)
def on_secret_deleted(instance: ManagedSecret, **kwargs):
    instance.delete_value()
