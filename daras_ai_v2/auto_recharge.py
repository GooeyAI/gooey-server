from datetime import datetime, timedelta, timezone

import stripe
from django.db.models import Sum
from django.utils import timezone
from loguru import logger

from app_users.models import AppUser, AppUserTransaction
from daras_ai_v2 import settings


def get_default_payment_method(user: AppUser) -> stripe.PaymentMethod | None:
    customer = user.search_stripe_customer()
    if not customer:
        return

    return _get_default_payment_method_for_customer(customer)


def _get_default_payment_method_for_customer(
    customer: stripe.Customer,
) -> stripe.PaymentMethod | None:
    pm_id = customer.invoice_settings.default_payment_method
    if not pm_id:
        return

    return stripe.PaymentMethod.retrieve(pm_id)


def auto_recharge_user(user: AppUser):
    if (
        not user.auto_recharge_enabled
        or user.balance >= user.auto_recharge_topup_threshold
    ):
        # user has disabled auto recharge or has enough balance
        return

    if not user.auto_recharge_amount:
        # user hasn't set the amount... should notify
        logger.error(f"User hasn't set auto recharge amount ({user=})")
        return

    if user.auto_recharge_amount > settings.AUTO_RECHARGE_MAX_AMOUNT:
        # user has set a very high amount... should notify
        logger.error(
            f"User has set very high auto recharge amount ({user=}, {user.auto_recharge_amount=})",
        )
        return

    customer = user.search_stripe_customer()
    if not customer:
        # user should be on stripe
        logger.error(f"User is not on stripe: {user=}")
        return

    if (
        dollars_spent := get_dollars_spent_this_month_by_user(user)
    ) >= user.auto_recharge_monthly_budget:
        # user has reached the monthly budget
        logger.info(f"User has reached the monthly budget: {user=}, {dollars_spent=}")
        # send an email to the user
        return

    invoice = get_or_create_auto_invoice(
        customer, amount_in_dollars=user.auto_recharge_amount
    )
    if invoice.status == "open":
        invoice.pay(payment_method=customer.invoice_settings.default_payment_method)
    elif invoice.status == "paid":
        logger.info(f"Auto recharge invoice already paid recently: {user=}, {invoice=}")


def get_or_create_auto_invoice(
    customer: stripe.Customer, amount_in_dollars: int
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

    logger.info(f"{invoices=}")

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
        user.auto_recharge_enabled and user.balance < user.auto_recharge_topup_threshold
    )
