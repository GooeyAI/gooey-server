import stripe
from loguru import logger

from app_users.models import AppUserTransaction
from celeryapp.celeryconfig import app
from payments.webhooks import set_free_subscription_for_user


@app.task
def after_stripe_addon(txn_id: int):
    txn = AppUserTransaction.objects.get(id=txn_id)

    default_pm = stripe_set_default_payment_method(txn)
    if default_pm and not txn.user.subscription:
        # user is not on an existing subscription... add one so that user can configure auto recharge
        subscription = set_free_subscription_for_user(uid=txn.user.uid)
        if (
            subscription.auto_recharge_enabled
            and not subscription.monthly_spending_budget
        ):
            subscription.monthly_spending_budget = int(3 * txn.charged_amount / 100)
            subscription.monthly_spending_notification_threshold = int(
                0.8 * subscription.monthly_spending_budget
            )
            subscription.save(
                update_fields=[
                    "monthly_spending_budget",
                    "monthly_spending_notification_threshold",
                ]
            )


def stripe_set_default_payment_method(
    instance: AppUserTransaction,
) -> stripe.PaymentMethod | None:
    # update customer's defualt payment method
    # note... that if a customer has an active subscription, the payment method attached there will be preferred
    # see `stripe_get_default_payment_method` in payments/models.py module
    invoice = stripe.Invoice.retrieve(
        instance.invoice_id, expand=["payment_intent", "payment_intent.payment_method"]
    )
    if (
        invoice.payment_intent
        and invoice.payment_intent.status == "succeeded"
        and invoice.payment_intent.payment_method
    ):
        if not invoice.payment_intent.payment_method.customer:
            logger.info(
                "Can't save payment method because it's not attached to a customer"
            )
            return

        logger.info(
            f"Updating default payment method for customer {invoice.customer} to {invoice.payment_intent.payment_method}"
        )
        stripe.Customer.modify(
            invoice.customer,
            invoice_settings={
                "default_payment_method": invoice.payment_intent.payment_method
            },
        )
        return invoice.payment_intent.payment_method
