from datetime import datetime, timezone

import stripe
from django.db import transaction
from fastapi import APIRouter
from fastapi.requests import Request
from furl import furl
from loguru import logger

from app_users.models import AppUser, PaymentProvider
from daras_ai_v2 import settings
from daras_ai_v2.billing import billing_page
from daras_ai_v2.send_email import send_email_via_postmark
from daras_ai_v2.settings import templates
from payments.models import PricingPlan, Subscription


BILLING_VERSION_KEY = "billing_version"
BILLING_VERSION_V2 = "v2"

account_url = str(furl(settings.APP_BASE_URL) / "account" / "v2")

app = APIRouter()


def billing_v2_tab(request: Request):
    return billing_page(request.user)


def handle_checkout_session_completed(uid: str, session_data):
    setup_intent_id = session_data.get("setup_intent")
    if not setup_intent_id:
        # not a setup mode checkout
        return

    # set default payment method
    user = AppUser.objects.get_or_create_from_uid(uid)[0]
    setup_intent = stripe.SetupIntent.retrieve(setup_intent_id)
    subscription_id = setup_intent.metadata.get("subscription_id")
    if not (
        user.subscription.payment_provider == PaymentProvider.STRIPE
        and user.subscription.external_id == subscription_id
    ):
        logger.error(f"Subscription {subscription_id} not found for user {user}")
        return

    stripe.Subscription.modify(
        subscription_id, default_payment_method=setup_intent.payment_method
    )


@transaction.atomic
def handle_subscription_updated(uid: str, subscription_data):
    logger.info("Subscription updated")

    metadata = subscription_data.metadata
    if metadata.get(BILLING_VERSION_KEY) != BILLING_VERSION_V2:
        logger.warning("Subscription metadata version is not 2")
        return

    product = stripe.Product.retrieve(subscription_data.plan.product)
    plan = PricingPlan.get_by_stripe_product(product)
    if not plan:
        raise Exception(
            f"PricingPlan not found for product {subscription_data.plan.product}"
        )

    if subscription_data.get("status") != "active":
        logger.warning(f"Subscription {subscription_data.id} is not active")
        return

    user = AppUser.objects.get_or_create_from_uid(uid)[0]
    if user.subscription and (
        user.subscription.payment_provider != PaymentProvider.STRIPE
        or user.subscription.external_id != subscription_data.id
    ):
        logger.warning(
            f"User {user} has different existing subscription {user.subscription}. Cancelling that..."
        )
        user.subscription.cancel()
        user.subscription.delete()
    elif not user.subscription:
        user.subscription = Subscription()

    user.subscription.plan = plan.value
    user.subscription.payment_provider = PaymentProvider.STRIPE
    user.subscription.external_id = subscription_data.id

    user.subscription.full_clean()
    user.subscription.save()
    user.save(update_fields=["subscription"])


def handle_subscription_cancelled(uid: str, subscription_data):
    metadata = subscription_data.metadata
    if metadata.get(BILLING_VERSION_KEY) != BILLING_VERSION_V2:
        logger.warning("Subscription metadata version is not 2")
        return

    subscription = Subscription.objects.get_by_stripe_subscription_id(
        subscription_data.id
    )
    logger.info(f"Subscription {subscription} cancelled. Deleting it...")
    subscription.delete()


@transaction.atomic
def send_monthly_spending_notification_email(user: AppUser):
    assert (
        user.subscription and user.subscription.monthly_spending_notification_threshold
    )

    if not user.email:
        logger.error(f"User doesn't have an email: {user=}")
        return

    send_email_via_postmark(
        from_address=settings.SUPPORT_EMAIL,
        to_address=user.email,
        subject=f"[Gooey.AI] Monthly spending has exceeded ${user.subscription.monthly_spending_notification_threshold}",
        html_body=templates.get_template(
            "monthly_spending_notification_threshold_email.html"
        ).render(
            user=user,
            account_url=account_url,
        ),
    )

    user.subscription.monthly_spending_notification_sent_at = datetime.now(
        tz=timezone.utc
    )
    user.subscription.save(update_fields=["monthly_spending_notification_sent_at"])
