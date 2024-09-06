from copy import copy

import stripe
from django.db import transaction
from loguru import logger

from app_users.models import PaymentProvider, TransactionReason
from daras_ai_v2 import paypal
from workspaces.models import Workspace
from .models import Subscription
from .plans import PricingPlan
from .tasks import (
    send_monthly_spending_notification_email,
    send_payment_failed_email_with_invoice,
)


class PaypalWebhookHandler:
    PROVIDER = PaymentProvider.PAYPAL

    @classmethod
    def handle_sale_completed(cls, sale: paypal.Sale):
        if not sale.billing_agreement_id:
            logger.info(f"sale {sale} is not a subscription sale... skipping")
            return

        pp_sub = paypal.Subscription.retrieve(sale.billing_agreement_id)
        assert pp_sub.custom_id, "pp_sub is missing workspace_id"
        assert pp_sub.plan_id, "pp_sub is missing plan ID"

        plan = PricingPlan.get_by_paypal_plan_id(pp_sub.plan_id)
        assert plan, f"Plan {pp_sub.plan_id} not found"

        charged_dollars = int(float(sale.amount.total))  # convert to dollars
        if charged_dollars != plan.monthly_charge:
            # log so that we can investigate, and record the payment as usual
            logger.critical(
                f"paypal: charged amount ${charged_dollars} does not match plan's monthly charge ${plan.monthly_charge}"
            )

        add_balance_for_payment(
            workspace_id_or_uid=pp_sub.custom_id,
            amount=plan.credits,
            invoice_id=sale.id,
            payment_provider=cls.PROVIDER,
            charged_amount=charged_dollars * 100,
            reason=TransactionReason.SUBSCRIBE,
            plan=plan.db_value,
        )

    @classmethod
    def handle_subscription_updated(cls, pp_sub: paypal.Subscription):
        logger.info(f"Paypal subscription updated {pp_sub.id}")

        assert (
            pp_sub.custom_id
        ), f"PayPal subscription {pp_sub.id} is missing workspace_id"
        assert pp_sub.plan_id, f"PayPal subscription {pp_sub.id} is missing plan ID"

        plan = PricingPlan.get_by_paypal_plan_id(pp_sub.plan_id)
        assert plan, f"Plan with id={pp_sub.plan_id} not found"

        if pp_sub.status.lower() != "active":
            logger.info(
                "Subscription is not active. Ignoring event", subscription=pp_sub
            )
            return

        set_workspace_subscription(
            workspace_id_or_uid=pp_sub.custom_id,
            plan=plan,
            provider=cls.PROVIDER,
            external_id=pp_sub.id,
        )

    @classmethod
    def handle_subscription_cancelled(cls, pp_sub: paypal.Subscription):
        assert pp_sub.custom_id, f"PayPal subscription {pp_sub.id} is missing uid"
        set_workspace_subscription(
            workspace_id_or_uid=pp_sub.custom_id,
            plan=PricingPlan.STARTER,
            provider=None,
            external_id=None,
        )


class StripeWebhookHandler:
    PROVIDER = PaymentProvider.STRIPE

    @classmethod
    def handle_invoice_paid(
        cls, workspace_id_or_uid: str | int, invoice: stripe.Invoice
    ):
        from app_users.tasks import save_stripe_default_payment_method

        kwargs = {}
        if invoice.subscription and invoice.subscription_details:
            kwargs["plan"] = PricingPlan.get_by_key(
                invoice.subscription_details.metadata.get("subscription_key")
            ).db_value
            match invoice.billing_reason:
                case "subscription_create":
                    reason = TransactionReason.SUBSCRIPTION_CREATE
                case "subscription_cycle":
                    reason = TransactionReason.SUBSCRIPTION_CYCLE
                case "subscription_update":
                    reason = TransactionReason.SUBSCRIPTION_UPDATE
                case _:
                    reason = TransactionReason.SUBSCRIBE
        elif invoice.metadata and invoice.metadata.get("auto_recharge"):
            reason = TransactionReason.AUTO_RECHARGE
        else:
            reason = TransactionReason.ADDON

        amount = invoice.lines.data[0].quantity
        charged_amount = invoice.lines.data[0].amount
        add_balance_for_payment(
            workspace_id_or_uid=workspace_id_or_uid,
            amount=amount,
            invoice_id=invoice.id,
            payment_provider=cls.PROVIDER,
            charged_amount=charged_amount,
            reason=reason,
            **kwargs,
        )

        save_stripe_default_payment_method.delay(
            workspace_id_or_uid=workspace_id_or_uid,
            payment_intent_id=invoice.payment_intent,
            amount=amount,
            charged_amount=charged_amount,
            reason=reason,
        )

    @classmethod
    def handle_checkout_session_completed(cls, workspace_id_or_uid: str, session_data):
        setup_intent_id = session_data.get("setup_intent")
        if not setup_intent_id:
            # not a setup mode checkout -- do nothing
            return

        setup_intent = stripe.SetupIntent.retrieve(setup_intent_id)
        if sub_id := setup_intent.metadata.get("subscription_id"):
            # subscription_id was passed to metadata when creating the session
            stripe.Subscription.modify(
                sub_id, default_payment_method=setup_intent.payment_method
            )
        elif customer_id := session_data.get("customer"):
            # no subscription_id, so update the customer's default payment method instead
            stripe.Customer.modify(
                customer_id,
                invoice_settings=dict(
                    default_payment_method=setup_intent.payment_method
                ),
            )

    @classmethod
    def handle_subscription_updated(
        cls, workspace_id_or_uid: int | str, stripe_sub: stripe.Subscription
    ):
        logger.info(f"Stripe subscription updated: {stripe_sub.id}")

        assert stripe_sub.plan, f"Stripe subscription {stripe_sub.id} is missing plan"
        assert (
            stripe_sub.plan.product
        ), f"Stripe subscription {stripe_sub.id} is missing product"

        product = stripe.Product.retrieve(stripe_sub.plan.product)
        plan = PricingPlan.get_by_stripe_product(product)
        if not plan:
            raise Exception(
                f"PricingPlan not found for product {stripe_sub.plan.product}"
            )

        if stripe_sub.status.lower() != "active":
            logger.info(
                "Subscription is not active. Ignoring event", subscription=stripe_sub
            )
            return

        set_workspace_subscription(
            workspace_id_or_uid=workspace_id_or_uid,
            plan=plan,
            provider=cls.PROVIDER,
            external_id=stripe_sub.id,
        )

    @classmethod
    def handle_subscription_cancelled(cls, workspace_id_or_uid: int | str):
        set_workspace_subscription(
            workspace_id_or_uid=workspace_id_or_uid,
            plan=PricingPlan.STARTER,
            provider=PaymentProvider.STRIPE,
            external_id=None,
        )

    @classmethod
    def handle_invoice_failed(cls, uid: str, data: dict):
        if stripe.Charge.list(payment_intent=data["payment_intent"], limit=1).has_more:
            # we must have already sent an invoice for this to the user. so we should just ignore this event
            logger.info("Charge already exists for this payment intent")
            return

        if data.get("metadata", {}).get("auto_recharge"):
            send_payment_failed_email_with_invoice.delay(
                uid=uid,
                invoice_url=data["hosted_invoice_url"],
                dollar_amt=data["amount_due"] / 100,
                subject="Payment failure on your Gooey.AI auto-recharge",
            )
        elif data.get("subscription_details", {}):
            send_payment_failed_email_with_invoice.delay(
                uid=uid,
                invoice_url=data["hosted_invoice_url"],
                dollar_amt=data["amount_due"] / 100,
                subject="Payment failure on your Gooey.AI subscription",
            )


def add_balance_for_payment(
    *,
    workspace_id_or_uid: int | str,
    amount: int,
    invoice_id: str,
    payment_provider: PaymentProvider,
    charged_amount: int,
    **kwargs,
):
    try:
        workspace = Workspace.objects.get(id=int(workspace_id_or_uid))
    except (ValueError, Workspace.DoesNotExist):
        workspace, _ = Workspace.objects.get_or_create_from_uid(workspace_id_or_uid)

    workspace.add_balance(
        amount=amount,
        invoice_id=invoice_id,
        charged_amount=charged_amount,
        payment_provider=payment_provider,
        **kwargs,
    )

    if not workspace.is_paying:
        workspace.is_paying = True
        workspace.save(update_fields=["is_paying"])

    if (
        workspace.subscription
        and workspace.subscription.should_send_monthly_spending_notification()
    ):
        send_monthly_spending_notification_email.delay(workspace.id)


def set_workspace_subscription(
    *,
    workspace_id_or_uid: int | str,
    plan: PricingPlan,
    provider: PaymentProvider | None,
    external_id: str | None,
    amount: int | None = None,
    charged_amount: int | None = None,
) -> Subscription:
    try:
        workspace = Workspace.objects.get(id=int(workspace_id_or_uid))
    except (ValueError, Workspace.DoesNotExist):
        workspace, _ = Workspace.objects.get_or_create_from_uid(workspace_id_or_uid)

    with transaction.atomic():
        old_sub = workspace.subscription
        if old_sub:
            new_sub = copy(old_sub)
        else:
            old_sub = None
            new_sub = Subscription()

        new_sub.plan = plan.db_value
        new_sub.payment_provider = provider
        new_sub.external_id = external_id
        new_sub.full_clean(amount=amount, charged_amount=charged_amount)
        new_sub.save()

        if not old_sub:
            workspace.subscription = new_sub
            workspace.save(update_fields=["subscription"])

    # cancel previous subscription if it's not the same as the new one
    if old_sub and old_sub.external_id != external_id:
        old_sub.cancel()

    return new_sub
