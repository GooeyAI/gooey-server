from loguru import logger

from app_users.models import AppUser, PaymentProvider
from payments.tasks import send_email_budget_reached, send_email_auto_recharge_failed


def auto_recharge_user(user: AppUser):
    if not user_should_auto_recharge(user):
        logger.info(f"User doesn't need to auto-recharge: {user=}")
        return

    dollars_spent = user.get_dollars_spent_this_month()
    if (
        dollars_spent + user.subscription.auto_recharge_topup_amount
        > user.subscription.monthly_spending_budget
    ):
        if not user.subscription.has_sent_monthly_budget_email_this_month():
            send_email_budget_reached.delay(user.id)
        logger.info(f"User has reached the monthly budget: {user=}, {dollars_spent=}")
        return

    match user.subscription.payment_provider:
        case PaymentProvider.STRIPE:
            customer = user.search_stripe_customer()
            if not customer:
                logger.error(f"User doesn't have a stripe customer: {user=}")
                return

            try:
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
            except Exception as e:
                logger.error(
                    f"Error while auto-recharging user: {user=}, {e=}, {invoice=}"
                )
                send_email_auto_recharge_failed.delay(user.id)

        case PaymentProvider.PAYPAL:
            logger.error(f"Auto-recharge not supported for PayPal: {user=}")
            return


def user_should_auto_recharge(user: AppUser):
    """
    whether an auto recharge should be attempted for the user
    """
    return (
        user.subscription
        and user.subscription.auto_recharge_enabled
        and user.balance < user.subscription.auto_recharge_balance_threshold
    )
