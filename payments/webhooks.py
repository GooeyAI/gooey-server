from urllib.parse import quote_plus

import stripe
from django.db import transaction
from loguru import logger
from requests.models import HTTPError

from .models import Subscription
from .plans import PricingPlan
from .tasks import send_monthly_spending_notification_email
from app_users.models import AppUser, PaymentProvider
from daras_ai_v2 import paypal


class WebhookHandler:
    PROVIDER: PaymentProvider

    @classmethod
    def _after_payment_completed(
        cls, *, uid: str, invoice_id: str, credits: int, charged_amount: int
    ):
        user = AppUser.objects.get_or_create_from_uid(uid)[0]
        user.add_balance(
            payment_provider=cls.PROVIDER,
            invoice_id=invoice_id,
            amount=credits,
            charged_amount=charged_amount,
        )
        if not user.is_paying:
            user.is_paying = True
            user.save(update_fields=["is_paying"])
        if (
            user.subscription
            and user.subscription.should_send_monthly_spending_notification()
        ):
            send_monthly_spending_notification_email.delay(kwargs={"uid": uid})

    @classmethod
    @transaction.atomic
    def _after_subscription_updated(cls, *, uid: str, sub_id: str, plan: PricingPlan):
        if not is_sub_active(provider=cls.PROVIDER, sub_id=sub_id):
            # subscription is not in an active state, just ignore
            logger.info(
                "Subscription is not active. Ignoring event",
                provider=cls.PROVIDER,
                sub_id=sub_id,
            )
            return

        user = AppUser.objects.get_or_create_from_uid(uid)[0]
        # select_for_update: we want to lock the row until we are done reading &
        # updating the subscription
        #
        # anther transaction shouldn't update the subscription in the meantime
        user: AppUser = AppUser.objects.select_for_update().get(pk=user.pk)
        if not user.subscription:
            # new subscription
            logger.info("Creating new subscription for user", uid=uid)
            user.subscription = Subscription.objects.get_or_create(
                payment_provider=cls.PROVIDER,
                external_id=sub_id,
                defaults={"plan": plan.db_value},
            )[0]
            user.subscription.plan = plan.db_value

        elif is_same_sub(user.subscription, provider=cls.PROVIDER, sub_id=sub_id):
            if user.subscription.plan == plan.db_value:
                # same subscription exists with the same plan in DB
                logger.info("Nothing to do")
                return
            else:
                # provider & sub_id is same, but plan is different. so we update only the plan
                logger.info("Updating plan for user", uid=uid)
                user.subscription.plan = plan.db_value

        else:
            logger.critical(
                "Invalid state: last subscription was not cleared for user", uid=uid
            )

            # we have a different existing subscription in DB
            # this is invalid state! we should cancel the subscription if it is active
            if is_sub_active(
                provider=user.subscription.payment_provider,
                sub_id=user.subscription.external_id,
            ):
                logger.critical(
                    "Found existing active subscription for user. Cancelling that...",
                    uid=uid,
                    provider=user.subscription.get_payment_provider_display(),
                    sub_id=user.subscription.external_id,
                )
                user.subscription.cancel()

            logger.info("Creating new subscription for user", uid=uid)
            user.subscription = Subscription(
                payment_provider=cls.PROVIDER, plan=plan, external_id=sub_id
            )

        user.subscription.full_clean()
        user.subscription.save()
        user.save(update_fields=["subscription"])

    @classmethod
    def _after_subscription_cancelled(cls, uid: str, sub_id: str):
        user = AppUser.objects.get_or_create_from_uid(uid=uid)[0]
        if user.subscription and is_same_sub(
            user.subscription, provider=cls.PROVIDER, sub_id=sub_id
        ):
            user.subscription = None
            user.save(update_fields=["subscription"])


class PaypalWebhookHandler(WebhookHandler):
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
        cls._after_payment_completed(
            uid=uid,
            invoice_id=sale.id,
            credits=plan.credits,
            charged_amount=charged_dollars * 100,
        )

    @classmethod
    def handle_subscription_updated(cls, pp_sub: paypal.Subscription):
        logger.info(f"Paypal subscription updated {pp_sub.id}")

        assert pp_sub.custom_id, f"PayPal subscription {pp_sub.id} is missing uid"
        assert pp_sub.plan_id, f"PayPal subscription {pp_sub.id} is missing plan ID"

        plan = PricingPlan.get_by_paypal_plan_id(pp_sub.plan_id)
        assert plan, f"Plan {pp_sub.plan_id} not found"

        cls._after_subscription_updated(
            uid=pp_sub.custom_id, sub_id=pp_sub.id, plan=plan
        )

    @classmethod
    def handle_subscription_cancelled(cls, pp_sub: paypal.Subscription):
        assert pp_sub.custom_id, f"PayPal subscription {pp_sub.id} is missing uid"
        cls._after_subscription_cancelled(uid=pp_sub.custom_id, sub_id=pp_sub.id)


class StripeWebhookHandler(WebhookHandler):
    PROVIDER = PaymentProvider.STRIPE

    @classmethod
    def handle_invoice_paid(cls, uid: str, invoice_data):
        invoice_id = invoice_data.id
        line_items = stripe.Invoice._static_request(
            "get",
            "/v1/invoices/{invoice}/lines".format(invoice=quote_plus(invoice_id)),
        )

        cls._after_payment_completed(
            uid=uid,
            invoice_id=invoice_id,
            credits=line_items.data[0].quantity,
            charged_amount=line_items.data[0].amount,
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

        if is_sub_active(provider=PaymentProvider.STRIPE, sub_id=sub_id):
            stripe.Subscription.modify(
                sub_id, default_payment_method=setup_intent.payment_method
            )

    @classmethod
    def handle_subscription_updated(cls, uid: str, stripe_sub):
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

        cls._after_subscription_updated(uid=uid, sub_id=stripe_sub.id, plan=plan)

    @classmethod
    def handle_subscription_cancelled(cls, uid: str, stripe_sub):
        logger.info(f"Stripe subscription cancelled: {stripe_sub.id}")

        cls._after_subscription_cancelled(uid=uid, sub_id=stripe_sub.id)


def is_same_sub(
    subscription: Subscription, *, provider: PaymentProvider, sub_id: str
) -> bool:
    return (
        subscription.payment_provider == provider and subscription.external_id == sub_id
    )


def is_sub_active(*, provider: PaymentProvider, sub_id: str) -> bool:
    match provider:
        case PaymentProvider.PAYPAL:
            try:
                sub = paypal.Subscription.retrieve(sub_id)
            except HTTPError as e:
                if e.response.status_code != 404:
                    # if not 404, it likely means there is a bug in our code...
                    # we want to know about it, but not break the end user experience
                    logger.exception(f"Unexpected PayPal error for sub: {sub_id}")
                return False

            return sub.status == "ACTIVE"

        case PaymentProvider.STRIPE:
            try:
                sub = stripe.Subscription.retrieve(sub_id)
            except stripe.error.InvalidRequestError as e:
                if e.http_status != 404:
                    # if not 404, it likely means there is a bug in our code...
                    # we want to know about it, but not break the end user experience
                    logger.exception(f"Unexpected Stripe error for sub: {sub_id}")
                return False
            except stripe.error.StripeError as e:
                logger.exception(f"Unexpected Stripe error for sub: {sub_id}")
                return False

            return sub.status == "active"
