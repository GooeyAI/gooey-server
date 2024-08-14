from loguru import logger
from django.db.models.signals import post_save
from django.dispatch import receiver

from app_users.models import AppUserTransaction, PaymentProvider, TransactionReason
from app_users.tasks import after_stripe_addon


@receiver(post_save, sender=AppUserTransaction)
def transaction_post_save(instance: AppUserTransaction, **kwargs):
    if not (
        instance.payment_provider == PaymentProvider.STRIPE
        and instance.reason == TransactionReason.ADDON
    ):
        return

    try:
        after_stripe_addon.delay(instance.pk)
    except Exception as e:
        logger.exception(e)
