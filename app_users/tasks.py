import stripe
from loguru import logger

from app_users.models import PaymentProvider, TransactionReason
from celeryapp.celeryconfig import app
from payments.plans import PricingPlan
from payments.webhooks import set_workspace_subscription
from workspaces.models import Workspace


@app.task
def save_stripe_default_payment_method(
    *,
    workspace_id_or_uid: int | str,
    payment_intent_id: str,
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
    if reason == TransactionReason.ADDON:
        try:
            workspace = Workspace.objects.select_related("subscription").get(
                int(workspace_id_or_uid)
            )
        except (ValueError, Workspace.DoesNotExist):
            workspace, _ = Workspace.objects.get_or_create_from_uid(workspace_id_or_uid)

        if workspace.subscription and (
            workspace.subscription.is_paid() or workspace.subscription.payment_provider
        ):
            # already has a subscription
            return

        set_workspace_subscription(
            workspace_id_or_uid=workspace.id,
            plan=PricingPlan.STARTER,
            provider=PaymentProvider.STRIPE,
            external_id=None,
            amount=amount,
            charged_amount=charged_amount,
        )
