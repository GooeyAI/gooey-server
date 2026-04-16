"""
Script to disable auto_recharge_enabled for subscriptions that don't qualify for credit topups.

This script sets auto_recharge_enabled=False for subscriptions where:
- The workspace is NOT on an Enterprise plan, AND
- The workspace has NO topup history (no ADDON or AUTO_RECHARGE transactions)

This ensures the auto_recharge setting matches the allow_credit_topups() policy.
"""

from time import sleep

from django.db.models import Exists, OuterRef

from app_users.models import AppUserTransaction, TransactionReason
from payments.models import Subscription
from payments.plans import PricingPlan

BATCH_SIZE = 10_000
DELAY = 0.1
SEP = " ... "


def run():
    """Main entry point for the script."""
    print("Finding subscriptions to disable auto-recharge...")

    # Subquery to check if workspace has topup history
    has_topup_history = AppUserTransaction.objects.filter(
        workspace=OuterRef("workspace"),
        reason__in=[TransactionReason.ADDON, TransactionReason.AUTO_RECHARGE],
    )

    # Find subscriptions that:
    # 1. Have auto_recharge_enabled = True (only update those currently enabled)
    # 2. Are NOT Enterprise plan (db_value != 6)
    # 3. Have NO topup history
    qs = (
        Subscription.objects.filter(
            auto_recharge_enabled=True,
        )
        .exclude(
            plan=PricingPlan.ENTERPRISE.db_value,
        )
        .annotate(has_topups=Exists(has_topup_history))
        .filter(
            has_topups=False,
        )
    )

    total_count = qs.count()
    print(f"Found {total_count} subscriptions to update")

    if total_count == 0:
        print("No subscriptions to update. Done!")
        return

    # Confirm before proceeding
    print("\nThis will disable auto-recharge for:")
    print("  - Non-Enterprise subscriptions")
    print("  - That have no topup purchase history")
    print(f"\nTotal affected: {total_count}")

    # Process in batches
    print(f"\nProcessing in batches of {BATCH_SIZE}...", end=SEP)
    update_in_batches(qs, auto_recharge_enabled=False)

    print(f"\n✓ Successfully updated {total_count} subscriptions")


def update_in_batches(qs, **kwargs):
    """
    Update queryset in batches to avoid overwhelming the database.

    Args:
        qs: Django queryset to update
        **kwargs: Field values to update
    """
    total = 0
    while True:
        # Get IDs of next batch and update them
        rows = qs.model.objects.filter(id__in=qs[:BATCH_SIZE]).update(**kwargs)
        sleep(DELAY)  # let the db breathe

        if not rows:
            print("Done!")
            break

        total += rows
        print(total, end=SEP, flush=True)


if __name__ == "__main__":
    run()
