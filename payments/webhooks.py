from copy import copy
from decimal import Decimal

import sentry_sdk
import stripe
from django.db import transaction
from loguru import logger

from app_users.models import PaymentProvider, TransactionReason
from daras_ai_v2 import paypal, settings
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
        assert pp_sub.custom_id, (
            f"PayPal subscription {pp_sub.id} is missing workspace_id/uid"
        )
        assert pp_sub.plan_id, f"PayPal subscription {pp_sub.id} is missing plan ID"

        plan = PricingPlan.get_by_paypal_plan_id(pp_sub.plan_id)
        assert plan, f"Plan {pp_sub.plan_id} not found"

        charged_dollars = int(float(sale.amount.total))  # convert to dollars
        if charged_dollars != plan.monthly_charge:
            # log so that we can investigate, and record the payment as usual
            logger.critical(
                f"paypal: charged amount ${charged_dollars} does not match plan's monthly charge ${plan.monthly_charge}"
            )

        add_balance_for_payment(
            workspace=Workspace.objects.from_pp_custom_id(pp_sub.custom_id),
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

        assert pp_sub.custom_id, (
            f"PayPal subscription {pp_sub.id} is missing workspace_id/uid"
        )
        assert pp_sub.plan_id, f"PayPal subscription {pp_sub.id} is missing plan ID"

        plan = PricingPlan.get_by_paypal_plan_id(pp_sub.plan_id)
        assert plan, f"Plan with id={pp_sub.plan_id} not found"

        if pp_sub.status.lower() != "active":
            logger.info(
                "Subscription is not active. Ignoring event", subscription=pp_sub
            )
            return

        set_workspace_subscription(
            provider=cls.PROVIDER,
            plan=plan,
            workspace=Workspace.objects.from_pp_custom_id(pp_sub.custom_id),
            external_id=pp_sub.id,
        )

    @classmethod
    def handle_subscription_cancelled(cls, pp_sub: paypal.Subscription):
        assert pp_sub.custom_id, f"PayPal subscription {pp_sub.id} is missing uid"
        set_workspace_subscription(
            workspace=Workspace.objects.from_pp_custom_id(pp_sub.custom_id),
            plan=PricingPlan.STARTER,
            provider=None,
            external_id=None,
        )


class StripeWebhookHandler:
    PROVIDER = PaymentProvider.STRIPE

    @classmethod
    def handle_invoice_paid(cls, workspace: Workspace, invoice: stripe.Invoice):
        from app_users.tasks import save_stripe_default_payment_method

        kwargs = {}
        if invoice.subscription and invoice.subscription_details:
            try:
                kwargs["plan"] = PricingPlan.get_by_key(
                    invoice.subscription_details.metadata.get(
                        settings.STRIPE_USER_SUBSCRIPTION_METADATA_FIELD
                    )
                ).db_value
            except KeyError as e:
                sentry_sdk.capture_exception(e)
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
            workspace=workspace,
            amount=amount,
            invoice_id=invoice.id,
            payment_provider=cls.PROVIDER,
            charged_amount=charged_amount,
            reason=reason,
            **kwargs,
        )

        save_stripe_default_payment_method.delay(
            payment_intent_id=invoice.payment_intent,
            workspace_id=workspace.id,
            amount=amount,
            charged_amount=charged_amount,
            reason=reason,
        )

    @classmethod
    def handle_checkout_session_completed(cls, session_data):
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
        cls, workspace: Workspace, stripe_sub: stripe.Subscription
    ):
        logger.info(f"Stripe subscription updated: {stripe_sub.id}")

        assert stripe_sub.plan, f"Stripe subscription {stripe_sub.id} is missing plan"
        assert stripe_sub.plan.product, (
            f"Stripe subscription {stripe_sub.id} is missing product"
        )

        try:
            plan = PricingPlan.get_by_key(
                stripe_sub.metadata[settings.STRIPE_USER_SUBSCRIPTION_METADATA_FIELD]
            )
        except KeyError:
            product = stripe.Product.retrieve(
                stripe_sub.plan.product, expand=["default_price"]
            )
            plan = PricingPlan.get_by_stripe_product(product)
            assert plan is not None, f"Plan for product {product.id} not found"

        if stripe_sub.status.lower() != "active":
            logger.info(
                "Subscription is not active. Ignoring event", subscription=stripe_sub
            )
            return

        amount = int(stripe_sub.quantity)
        charged_amount = round(Decimal(stripe_sub.plan.amount_decimal) * amount)

        set_workspace_subscription(
            provider=cls.PROVIDER,
            plan=plan,
            workspace=workspace,
            external_id=stripe_sub.id,
            amount=amount,
            charged_amount=charged_amount,
        )

    @classmethod
    def handle_subscription_cancelled(cls, workspace: Workspace):
        set_workspace_subscription(
            workspace=workspace,
            plan=PricingPlan.STARTER,
            provider=PaymentProvider.STRIPE,
            external_id=None,
        )

    @classmethod
    def handle_invoice_failed(cls, workspace: Workspace, data: dict):
        if stripe.Charge.list(payment_intent=data["payment_intent"], limit=1).has_more:
            # we must have already sent an invoice for this to the user. so we should just ignore this event
            logger.info("Charge already exists for this payment intent")
            return

        if data.get("metadata", {}).get("auto_recharge"):
            send_payment_failed_email_with_invoice.delay(
                workspace_id=workspace.id,
                invoice_url=data["hosted_invoice_url"],
                dollar_amt=data["amount_due"] / 100,
                subject="Payment failure on your Gooey.AI auto-recharge",
            )
        elif data.get("subscription_details", {}):
            send_payment_failed_email_with_invoice.delay(
                workspace_id=workspace.id,
                invoice_url=data["hosted_invoice_url"],
                dollar_amt=data["amount_due"] / 100,
                subject="Payment failure on your Gooey.AI subscription",
            )


def add_balance_for_payment(
    *,
    workspace: Workspace,
    amount: int,
    invoice_id: str,
    payment_provider: PaymentProvider,
    charged_amount: int,
    **kwargs,
):
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
        send_monthly_spending_notification_email.delay(workspace_id=workspace.id)


def set_workspace_subscription(
    *,
    workspace: Workspace,
    plan: PricingPlan,
    provider: PaymentProvider | None,
    external_id: str | None,
    amount: int = 0,
    charged_amount: int = 0,
    cancel_old: bool = True,
) -> Subscription:
    with transaction.atomic():
        old_sub = workspace.subscription
        if old_sub:
            new_sub = copy(old_sub)
        else:
            old_sub = None
            new_sub = Subscription()

        new_sub.plan = plan.db_value
        new_sub.amount = amount
        new_sub.charged_amount = charged_amount
        new_sub.payment_provider = provider
        new_sub.external_id = external_id
        new_sub.full_clean()
        new_sub.save()

        if not old_sub:
            workspace.subscription = new_sub
            workspace.save(update_fields=["subscription"])

    # cancel previous subscription if it's not the same as the new one
    if cancel_old and old_sub and old_sub.external_id != external_id:
        old_sub.cancel()

    return new_sub
