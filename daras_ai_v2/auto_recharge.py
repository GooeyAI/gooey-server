from contextlib import contextmanager
from datetime import datetime, timezone

from django.utils import timezone
from furl import furl
from loguru import logger

from app_users.models import AppUser, AppUserTransaction, PaymentProvider
from daras_ai_v2 import settings
from daras_ai_v2.settings import templates
from daras_ai_v2.send_email import send_email_via_postmark


def send_email_auto_recharge_failed(user: AppUser, reason: str):
    if not user.email:
        return

    email_body = templates.get_template("auto_recharge_failed_email.html").render(
        user=user,
        account_url=get_account_url(),
        reason=reason,
    )
    send_email_via_postmark(
        from_address=settings.SUPPORT_EMAIL,
        to_address=user.email,
        subject="[Gooey.AI] Auto-Recharge failed",
        html_body=email_body,
    )


def auto_recharge_user(user: AppUser):
    if not user_should_auto_recharge(user):
        logger.info(f"User doesn't need to auto-recharge: {user=}")
        return

    if not user.subscription.auto_recharge_topup_amount:
        send_email_auto_recharge_failed(user, reason="recharge amount wasn't set")
        logger.error(f"User hasn't set auto recharge amount ({user=})")
        return

    dollars_spent = user.get_dollars_spent_this_month()
    if (
        dollars_spent + user.subscription.auto_recharge_topup_amount
        > user.subscription.monthly_spending_budget
    ):
        send_email_auto_recharge_failed(
            user, reason="you have reached your monthly budget"
        )
        logger.info(f"User has reached the monthly budget: {user=}, {dollars_spent=}")
        return

    match user.subscription.payment_provider:
        case PaymentProvider.STRIPE:
            customer = user.search_stripe_customer()
            if not customer:
                logger.error(f"User doesn't have a stripe customer: {user=}")
                return

            with email_user_if_fails(user, reason="the payment failed"):
                invoice = user.subscription.stripe_get_or_create_auto_invoice(
                    amount_in_dollars=user.subscription.auto_recharge_topup_amount,
                    metadata_key="auto_recharge",
                )

                if invoice.status == "open":
                    pm = user.subscription.stripe_get_default_payment_method()
                    invoice.pay(payment_method=pm)
                    logger.info(
                        f"Payment attempted for auto recharge invoice: {user=}, {invoice=}"
                    )
                elif invoice.status == "paid":
                    logger.info(
                        f"Auto recharge invoice already paid recently: {user=}, {invoice=}"
                    )

        case PaymentProvider.PAYPAL:
            logger.error(f"Auto-recharge not supported for PayPal: {user=}")
            return


def user_should_auto_recharge(user: AppUser):
    return (
        user.subscription
        and user.subscription.auto_recharge_enabled
        and user.balance < user.subscription.auto_recharge_balance_threshold
    )


def get_account_url():
    return str(furl(settings.APP_BASE_URL) / "account" / "")


@contextmanager
def email_user_if_fails(user: AppUser, reason: str):
    try:
        yield
    except Exception:
        send_email_auto_recharge_failed(user, reason=reason)
        raise
