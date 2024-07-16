import stripe
from django.db import transaction
from loguru import logger

from app_users.models import AppUser, PaymentProvider, TransactionReason
from daras_ai_v2 import paypal
from .models import Subscription
from .plans import PricingPlan
from .tasks import send_monthly_spending_notification_email


class PaypalWebhookHandler:
    PROVIDER = PaymentProvider.PAYPAL

    @classmethod
    def handle_sale_completed(cls, sale: paypal.Sale):
        if not sale.billing_agreement_id:
            logger.info(f"sale {sale} is not a subscription sale... skipping")
            return

        pp_sub = paypal.Subscription.retrieve(sale.billing_agreement_id)
        assert pp_sub.custom_id, "pp_sub is missing uid"
        assert pp_sub.plan_id, "pp_sub is missing plan ID"

        plan = PricingPlan.get_by_paypal_plan_id(pp_sub.plan_id)
        assert plan, f"Plan {pp_sub.plan_id} not found"

        charged_dollars = int(float(sale.amount.total))  # convert to dollars
        if charged_dollars != plan.monthly_charge:
            # log so that we can investigate, and record the payment as usual
            logger.critical(
                f"paypal: charged amount ${charged_dollars} does not match plan's monthly charge ${plan.monthly_charge}"
            )

        uid = pp_sub.custom_id
        add_balance_for_payment(
            uid=uid,
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

        assert pp_sub.custom_id, f"PayPal subscription {pp_sub.id} is missing uid"
        assert pp_sub.plan_id, f"PayPal subscription {pp_sub.id} is missing plan ID"

        plan = PricingPlan.get_by_paypal_plan_id(pp_sub.plan_id)
        assert plan, f"Plan with id={pp_sub.plan_id} not found"

        if pp_sub.status.lower() != "active":
            logger.info(
                "Subscription is not active. Ignoring event", subscription=pp_sub
            )
            return

        _set_user_subscription(
            provider=cls.PROVIDER,
            plan=plan,
            uid=pp_sub.custom_id,
            external_id=pp_sub.id,
        )

    @classmethod
    def handle_subscription_cancelled(cls, pp_sub: paypal.Subscription):
        assert pp_sub.custom_id, f"PayPal subscription {pp_sub.id} is missing uid"
        _remove_subscription_for_user(
            provider=cls.PROVIDER, uid=pp_sub.custom_id, external_id=pp_sub.id
        )


class StripeWebhookHandler:
    PROVIDER = PaymentProvider.STRIPE

    @classmethod
    def handle_invoice_paid(cls, uid: str, invoice: stripe.Invoice):
        kwargs = {}
        if invoice.subscription:
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
        add_balance_for_payment(
            uid=uid,
            amount=invoice.lines.data[0].quantity,
            invoice_id=invoice.id,
            payment_provider=cls.PROVIDER,
            charged_amount=invoice.lines.data[0].amount,
            reason=reason,
            **kwargs,
        )

    @classmethod
    def handle_checkout_session_completed(cls, uid: str, session_data):
        if setup_intent_id := session_data.get("setup_intent") is None:
            # not a setup mode checkout -- do nothing
            return
        setup_intent = stripe.SetupIntent.retrieve(setup_intent_id)

        # subscription_id was passed to metadata when creating the session
        sub_id = setup_intent.metadata["subscription_id"]
        assert (
            sub_id
        ), f"subscription_id is missing in setup_intent metadata {setup_intent}"

        stripe.Subscription.modify(
            sub_id, default_payment_method=setup_intent.payment_method
        )

    @classmethod
    def handle_subscription_updated(cls, uid: str, stripe_sub: stripe.Subscription):
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

        _set_user_subscription(
            provider=cls.PROVIDER,
            plan=plan,
            uid=uid,
            external_id=stripe_sub.id,
        )

    @classmethod
    def handle_subscription_cancelled(cls, uid: str, stripe_sub):
        logger.info(f"Stripe subscription cancelled: {stripe_sub.id}")
        _remove_subscription_for_user(
            provider=cls.PROVIDER, uid=uid, external_id=stripe_sub.id
        )


def add_balance_for_payment(
    *,
    uid: str,
    amount: int,
    invoice_id: str,
    payment_provider: PaymentProvider,
    charged_amount: int,
    **kwargs,
):
    user = AppUser.objects.get_or_create_from_uid(uid)[0]
    user.add_balance(
        amount=amount,
        invoice_id=invoice_id,
        charged_amount=charged_amount,
        payment_provider=payment_provider,
        **kwargs,
    )

    if not user.is_paying:
        user.is_paying = True
        user.save(update_fields=["is_paying"])

    if (
        user.subscription
        and user.subscription.should_send_monthly_spending_notification()
    ):
        send_monthly_spending_notification_email.delay(user.id)


def _set_user_subscription(
    *, provider: PaymentProvider, plan: PricingPlan, uid: str, external_id: str
):
    with transaction.atomic():
        subscription, created = Subscription.objects.get_or_create(
            payment_provider=provider,
            external_id=external_id,
            defaults=dict(plan=plan.db_value),
        )
        subscription.plan = plan.db_value
        subscription.full_clean()
        subscription.save()

        user = AppUser.objects.get_or_create_from_uid(uid)[0]
        existing = user.subscription

        user.subscription = subscription
        user.save(update_fields=["subscription"])

    if not existing:
        return

    # cancel existing subscription if it's not the same as the new one
    if existing.external_id != external_id:
        existing.cancel()

    # delete old db record if it exists
    if existing.id != subscription.id:
        existing.delete()


def _remove_subscription_for_user(
    *, uid: str, provider: PaymentProvider, external_id: str
):
    AppUser.objects.filter(
        uid=uid,
        subscription__payment_provider=provider,
        subscription__external_id=external_id,
    ).update(
        subscription=None,
    )
