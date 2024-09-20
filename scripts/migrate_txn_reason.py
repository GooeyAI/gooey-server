from app_users.models import TransactionReason, AppUserTransaction
from payments.plans import PricingPlan


def run():
    for transaction in AppUserTransaction.objects.filter(amount__gt=0):
        # For old transactions, we didn't have a subscription field.
        # It just so happened that all monthly subscriptions we offered had
        # different amounts from the one-time purchases.
        # This uses that heuristic to determine whether a transaction
        # was a subscription payment or a one-time purchase.
        transaction.reason = TransactionReason.ADDON
        for plan in PricingPlan:
            if (
                transaction.amount == plan.credits
                and transaction.charged_amount == plan.monthly_charge * 100
            ):
                transaction.plan = plan.db_value
                transaction.reason = TransactionReason.SUBSCRIBE
                break
        transaction.save(update_fields=["reason", "plan"])
