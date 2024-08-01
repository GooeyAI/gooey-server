import stripe
from loguru import logger
from django.db.models.signals import post_save
from django.dispatch import receiver

from app_users.models import AppUserTransaction, PaymentProvider, TransactionReason
from payments.plans import PricingPlan
from payments.webhooks import set_user_subscription


@receiver(post_save, sender=AppUserTransaction)
def after_stripe_addon(instance: AppUserTransaction, **kwargs):
    if not (
        instance.payment_provider == PaymentProvider.STRIPE
        and instance.reason == TransactionReason.ADDON
    ):
        return

    set_default_payment_method(instance)
    set_free_subscription_on_user(instance)


def set_default_payment_method(instance: AppUserTransaction):
    # update customer's defualt payment method
    # note... that if a customer has an active subscription, the payment method attached there will be preferred
    # see `stripe_get_default_payment_method` in payments/models.py module
    invoice = stripe.Invoice.retrieve(instance.invoice_id, expand=["payment_intent"])
    if (
        invoice.payment_intent
        and invoice.payment_intent.status == "succeeded"
        and invoice.payment_intent.payment_method
    ):
        logger.info(
            f"Updating default payment method for customer {invoice.customer} to {invoice.payment_intent.payment_method}"
        )
        stripe.Customer.modify(
            invoice.customer,
            invoice_settings={
                "default_payment_method": invoice.payment_intent.payment_method
            },
        )


def set_free_subscription_on_user(instance: AppUserTransaction):
    user = instance.user
    if user.subscription:
        return

    set_user_subscription(
        provider=PaymentProvider.STRIPE,
        plan=PricingPlan.STARTER,
        uid=user.uid,
        external_id=None,
    )
