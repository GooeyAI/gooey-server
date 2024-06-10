from datetime import datetime, timedelta, timezone

from app_users.models import AppUser, PaymentProvider
from daras_ai_v2 import settings
from daras_ai_v2.redis_cache import redis_lock


class AutoRechargeException(Exception):
    pass


class MonthlyBudgetReachedException(AutoRechargeException):
    def __init__(self, *args, budget: int, spending: float, **kwargs):
        super().__init__(*args, **kwargs)
        self.budget = budget
        self.spending = spending


class PaymentFailedException(AutoRechargeException):
    pass


class AutoRechargeCooldownException(AutoRechargeException):
    pass


def auto_recharge_user(uid: str):
    with redis_lock(f"gooey/auto_recharge_user/{uid}"):
        user: AppUser = AppUser.objects.get(uid=uid)
        if should_attempt_auto_recharge(user):
            _auto_recharge_user(user)


def _auto_recharge_user(user: AppUser):
    """
    Returns whether a charge was attempted
    """
    from payments.webhooks import StripeWebhookHandler

    assert (
        user.subscription.payment_provider == PaymentProvider.STRIPE
    ), "Auto recharge is only supported with Stripe"

    # check for monthly budget
    dollars_spent = user.get_dollars_spent_this_month()
    if (
        dollars_spent + user.subscription.auto_recharge_topup_amount
        > user.subscription.monthly_spending_budget
    ):
        raise MonthlyBudgetReachedException(
            "Performing this top-up would exceed your monthly recharge budget",
            budget=user.subscription.monthly_spending_budget,
            spending=dollars_spent,
        )

    # create invoice or get a recent one (recent = created in the last `settings.AUTO_RECHARGE_COOLDOWN_SECONDS` seconds)
    cooldown_period_start = datetime.now(timezone.utc) - timedelta(
        seconds=settings.AUTO_RECHARGE_COOLDOWN_SECONDS
    )
    try:
        invoice = user.subscription.stripe_get_or_create_auto_invoice(
            amount_in_dollars=user.subscription.auto_recharge_topup_amount,
            metadata_key="auto_recharge",
            created_after=cooldown_period_start,
        )
    except Exception as e:
        raise PaymentFailedException("Failed to create auto-recharge invoice") from e

    # recent invoice was already paid
    if invoice.status == "paid":
        raise AutoRechargeCooldownException(
            "An auto recharge invoice was paid recently"
        )

    # get default payment method and attempt payment
    assert invoice.status == "open"  # sanity check
    pm = user.subscription.stripe_get_default_payment_method()

    try:
        invoice_data = invoice.pay(payment_method=pm)
    except Exception as e:
        raise PaymentFailedException(
            "Payment failed when attempting to auto-recharge"
        ) from e
    else:
        assert invoice_data.paid
        StripeWebhookHandler.handle_invoice_paid(
            uid=user.uid, invoice_data=invoice_data
        )


def should_attempt_auto_recharge(user: AppUser):
    return (
        user.subscription
        and user.subscription.auto_recharge_enabled
        and user.subscription.payment_provider
        and user.balance < user.subscription.auto_recharge_balance_threshold
    )
