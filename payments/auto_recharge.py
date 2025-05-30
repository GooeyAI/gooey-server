import traceback

import sentry_sdk
from loguru import logger

from app_users.models import PaymentProvider
from daras_ai_v2.redis_cache import redis_lock
from workspaces.models import Workspace
from payments.tasks import send_monthly_budget_reached_email


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


def should_attempt_auto_recharge(workspace: Workspace) -> bool:
    return bool(
        workspace.subscription
        and workspace.subscription.auto_recharge_enabled
        and workspace.subscription.payment_provider
        and workspace.balance < workspace.subscription.auto_recharge_balance_threshold
    )


def run_auto_recharge_gracefully(workspace: Workspace):
    """
    Wrapper over _auto_recharge_workspace, that handles exceptions so that it can:
    - log exceptions
    - send emails when auto-recharge fails
    - not retry if this is run as a background task

    Meant to be used in conjunction with should_attempt_auto_recharge
    """
    try:
        with redis_lock(f"gooey/auto_recharge_user/v1/{workspace.id}"):
            _auto_recharge_workspace(workspace)
    except AutoRechargeCooldownException as e:
        logger.info(
            f"Rejected auto-recharge because auto-recharge is in cooldown period for workspace"
            f"{workspace=}, {e=}"
        )
    except MonthlyBudgetReachedException as e:
        send_monthly_budget_reached_email(workspace)
        logger.info(
            f"Rejected auto-recharge because user has reached monthly budget"
            f"{workspace=}, spending=${e.spending}, budget=${e.budget}"
        )
    except Exception as e:
        traceback.print_exc()
        sentry_sdk.capture_exception(e)


def _auto_recharge_workspace(workspace: Workspace):
    """
    Returns whether a charge was attempted
    """
    from payments.webhooks import StripeWebhookHandler

    assert workspace.subscription.payment_provider == PaymentProvider.STRIPE, (
        "Auto recharge is only supported with Stripe"
    )

    # check for monthly budget
    dollars_spent = workspace.get_dollars_spent_this_month()
    if (
        dollars_spent + workspace.subscription.auto_recharge_topup_amount
        > workspace.subscription.monthly_spending_budget
    ):
        raise MonthlyBudgetReachedException(
            "Performing this top-up would exceed your monthly recharge budget",
            budget=workspace.subscription.monthly_spending_budget,
            spending=dollars_spent,
        )

    try:
        invoice = workspace.subscription.stripe_get_or_create_auto_invoice(
            amount_in_dollars=workspace.subscription.auto_recharge_topup_amount,
            metadata_key="auto_recharge",
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
    pm = workspace.subscription.stripe_get_default_payment_method()
    if not pm:
        logger.warning(
            f"{workspace} has no default payment method, cannot auto-recharge"
        )
        return

    try:
        invoice_data = invoice.pay(payment_method=pm)
    except Exception as e:
        raise PaymentFailedException(
            "Payment failed when attempting to auto-recharge"
        ) from e
    else:
        assert invoice_data.paid
        StripeWebhookHandler.handle_invoice_paid(workspace, invoice_data)
