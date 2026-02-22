import stripe
from loguru import logger

from app_users.models import PaymentProvider, TransactionReason
from celeryapp.celeryconfig import app
from payments.models import Subscription
from payments.plans import PricingPlan
from payments.webhooks import set_workspace_subscription
from workspaces.models import Workspace


@app.task
def save_stripe_default_payment_method(
    *,
    payment_intent_id: str,
    workspace_id: int,
    amount: int,
    charged_amount: int,
    reason: TransactionReason,
):
    pi = stripe.PaymentIntent.retrieve(payment_intent_id, expand=["payment_method"])
    pm = pi.payment_method
    if not (pm and pm.customer):
        logger.error(
            f"Failed to retrieve payment method for payment intent {payment_intent_id}"
        )
        return

    # update customer's defualt payment method
    # note: if a customer has an active subscription, the payment method attached there will be preferred
    # see `stripe_get_default_payment_method` in payments/models.py module
    logger.info(
        f"Updating default payment method for customer {pm.customer} to {pm.id}"
    )
    stripe.Customer.modify(
        pm.customer,
        invoice_settings=dict(default_payment_method=pm),
    )

    # if user already has a subscription with payment info, we do nothing
    # otherwise, we set the user's subscription to the free plan
    if (
        reason == TransactionReason.ADDON
        and not Subscription.objects.filter(
            workspace__id=workspace_id, payment_provider__isnull=False
        ).exists()
    ):
        set_workspace_subscription(
            workspace=Workspace.objects.get(id=workspace_id),
            plan=PricingPlan.STARTER,
            provider=PaymentProvider.STRIPE,
            external_id=None,
        )
