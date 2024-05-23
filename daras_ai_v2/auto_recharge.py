from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import stripe
from django.db.models import Sum
from django.utils import timezone
from furl import furl
from loguru import logger

from app_users.models import AppUser, AppUserTransaction, PaymentProvider
from daras_ai_v2 import paypal, settings
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


def send_email_monthly_spend_threshold_reached(user: AppUser):
    if not user.email:
        return

    email_body = templates.get_template(
        "monthly_spend_threshold_reached_email.html"
    ).render(
        user=user,
        account_url=get_account_url(),
    )
    send_email_via_postmark(
        from_address=settings.SUPPORT_EMAIL,
        to_address=user.email,
        subject="[Gooey.AI] Monthly Spend Threshold Reached",
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

    dollars_spent = get_dollars_spent_this_month_by_user(user)
    if (
        dollars_spent + user.subscription.auto_recharge_topup_amount
        > user.monthly_spending_budget
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

            sub = stripe.Subscription.retrieve(user.subscription.external_id)
            pm = sub.default_payment_method
            with email_user_if_fails(user, reason="the payment failed"):
                invoice = stripe_get_or_create_auto_invoice(
                    customer=customer,
                    amount_in_dollars=user.subscription.auto_recharge_topup_amount,
                )

                if invoice.status == "open":
                    invoice.pay(payment_method=pm)
                    logger.info(
                        f"Payment attempted for auto recharge invoice: {user=}, {invoice=}"
                    )
                elif invoice.status == "paid":
                    logger.info(
                        f"Auto recharge invoice already paid recently: {user=}, {invoice=}"
                    )

        case PaymentProvider.PAYPAL:
            subscription = paypal.Subscription.retrieve(user.subscription.external_id)
            if not subscription.billing_info:
                logger.error(f"Subscription doesn't have billing info: {user=}")
                return

            if last_payment := subscription.billing_info.last_payment:
                if last_payment.time - datetime.now(tz=timezone.utc) < timedelta(
                    seconds=settings.AUTO_RECHARGE_COOLDOWN_SECONDS
                ):
                    logger.info(
                        f"Last payment was within cooldown interval, skipping...: {user=}, {subscription.billing_info.last_payment=}"
                    )
                    return

            if float(subscription.billing_info.outstanding_balance.total) != 0.0:
                logger.warning(
                    f"Subscription has outstanding balance already, attempting to charge: {user=}",
                )
                subscription.capture(
                    note="Attempting payment of outstanding balance due to low credits",
                    amount=subscription.billing_info.outstanding_balance,
                )
                return

            amount = paypal.Amount.USD(subscription.auto_recharge_topup_amount)

            logger.info(f"Auto-recharging user: {user=}, {amount=}")
            with email_user_if_fails(user, reason="the payment failed"):
                subscription.set_outstanding_balance(amount=amount)
                subscription.capture(
                    note="Auto-recharge due to low credits", amount=amount
                )


def stripe_get_or_create_auto_invoice(
    customer: stripe.Customer,
    amount_in_dollars: int,
) -> stripe.Invoice:
    """
    Fetches the relevant auto recharge invoice, or creates one if it doesn't exist.

    This is the fallback order:
    - Fetch an open auto_recharge invoice
    - Fetch an auto_recharge invoice that was recently paid
    - Create an invoice with amount=amount_in_dollars
    """
    invoices = stripe.Invoice.list(
        customer=customer,
        collection_method="charge_automatically",
    )
    invoices = [inv for inv in invoices.data if "auto_recharge" in inv.metadata]

    open_invoice = next((inv for inv in invoices if inv.status == "open"), None)
    if open_invoice:
        return open_invoice

    recently_paid_invoice = next(
        (
            inv
            for inv in invoices
            if inv.status == "paid"
            and datetime.now(tz=timezone.utc).timestamp() - inv.created
            < settings.AUTO_RECHARGE_COOLDOWN_SECONDS
        ),
        None,
    )
    if recently_paid_invoice:
        return recently_paid_invoice

    invoice = stripe.Invoice.create(
        customer=customer,
        collection_method="charge_automatically",
        metadata={"auto_recharge": True},
        auto_advance=False,
        pending_invoice_items_behavior="exclude",
    )
    stripe.InvoiceItem.create(
        customer=customer,
        invoice=invoice,
        price_data={
            "currency": "usd",
            "product": settings.STRIPE_ADDON_CREDITS_PRODUCT_ID,
            "unit_amount_decimal": (
                settings.ADDON_CREDITS_PER_DOLLAR / 100
            ),  # in cents
        },
        quantity=amount_in_dollars * settings.ADDON_CREDITS_PER_DOLLAR,
        currency="usd",
        metadata={"auto_recharge": True},
    )
    invoice.finalize_invoice(auto_advance=True)
    return invoice


def get_dollars_spent_this_month_by_user(user: AppUser):
    today = datetime.now(tz=timezone.utc)
    cents_spent = AppUserTransaction.objects.filter(
        user=user,
        created_at__month=today.month,
        created_at__year=today.year,
        amount__gt=0,
    ).aggregate(total=Sum("charged_amount"))["total"]
    return (cents_spent or 0) / 100


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
