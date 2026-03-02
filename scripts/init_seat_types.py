from __future__ import annotations

from dataclasses import dataclass

from payments.plans import PricingPlan
from workspaces.models import Workspace, WorkspaceSeatType

GOOEY_ADMIN_SEAT_TYPE_NAME = "Gooey Admin"
DEFAULT_PLAN_SEAT_TYPES: dict[PricingPlan, list[dict[str, int]]] = {
    PricingPlan.STANDARD: [
        {"monthly_charge": 25, "monthly_credit_limit": 2_000},
        {"monthly_charge": 50, "monthly_credit_limit": 4_200},
        {"monthly_charge": 100, "monthly_credit_limit": 9_000},
        {"monthly_charge": 200, "monthly_credit_limit": 20_000},
        {"monthly_charge": 300, "monthly_credit_limit": 32_000},
        {"monthly_charge": 400, "monthly_credit_limit": 44_000},
    ],
    PricingPlan.TEAM: [
        {"monthly_charge": 40, "monthly_credit_limit": 2_500},
        {"monthly_charge": 60, "monthly_credit_limit": 5_000},
        {"monthly_charge": 110, "monthly_credit_limit": 9_000},
        {"monthly_charge": 200, "monthly_credit_limit": 20_000},
        {"monthly_charge": 300, "monthly_credit_limit": 32_000},
        {"monthly_charge": 400, "monthly_credit_limit": 44_000},
    ],
}


@dataclass(frozen=True)
class SeedStats:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    subscriptions_updated: int = 0
    workspaces_updated: int = 0


def _default_seat_type_name(*, monthly_credit_limit: int) -> str:
    return f"{monthly_credit_limit:,} credits/month"


def _plan_for_workspace(workspace: Workspace) -> PricingPlan | None:
    if not workspace.subscription:
        return None
    plan = PricingPlan.from_sub(workspace.subscription)
    if plan in (PricingPlan.TEAM, PricingPlan.STANDARD):
        return plan
    return None


def _resolve_subscription_workspace_seat_type(
    plan: PricingPlan, workspace: Workspace
) -> WorkspaceSeatType:
    assert workspace.subscription is not None

    candidate_qs = WorkspaceSeatType.objects.exclude(name=GOOEY_ADMIN_SEAT_TYPE_NAME)
    current = workspace.subscription.get_seat_type()
    if current:
        match = candidate_qs.filter(
            monthly_charge=current.monthly_charge,
            monthly_credit_limit=current.monthly_credit_limit,
        ).first()
        if match:
            return match
        match = candidate_qs.filter(monthly_charge=current.monthly_charge).first()
        if match:
            return match

    default_plan_seat_type = DEFAULT_PLAN_SEAT_TYPES[plan][0]
    match = candidate_qs.filter(
        monthly_charge=default_plan_seat_type["monthly_charge"],
        monthly_credit_limit=default_plan_seat_type["monthly_credit_limit"],
    ).first()
    if match:
        return match

    fallback = candidate_qs.order_by("monthly_charge", "id").first()
    if fallback:
        return fallback
    raise WorkspaceSeatType.DoesNotExist(
        f"No billable workspace seat type found for workspace_id={workspace.id}"
    )


def run(*_args):
    stats = SeedStats()

    # seed global seat types (shared across workspaces)
    for plan, seat_types in DEFAULT_PLAN_SEAT_TYPES.items():
        for seat_type in seat_types:
            _, created = WorkspaceSeatType.objects.update_or_create(
                name=_default_seat_type_name(
                    monthly_credit_limit=seat_type["monthly_credit_limit"]
                ),
                defaults=dict(
                    monthly_charge=seat_type["monthly_charge"],
                    monthly_credit_limit=seat_type["monthly_credit_limit"],
                ),
            )
            if created:
                stats = SeedStats(
                    created=stats.created + 1,
                    updated=stats.updated,
                    skipped=stats.skipped,
                    subscriptions_updated=stats.subscriptions_updated,
                    workspaces_updated=stats.workspaces_updated,
                )
            else:
                stats = SeedStats(
                    created=stats.created,
                    updated=stats.updated + 1,
                    skipped=stats.skipped,
                    subscriptions_updated=stats.subscriptions_updated,
                    workspaces_updated=stats.workspaces_updated,
                )

    _, admin_created = WorkspaceSeatType.objects.update_or_create(
        name=GOOEY_ADMIN_SEAT_TYPE_NAME,
        defaults=dict(
            monthly_charge=0,
            monthly_credit_limit=2_500,
            daily_credit_limit=None,
        ),
    )
    if admin_created:
        stats = SeedStats(
            created=stats.created + 1,
            updated=stats.updated,
            skipped=stats.skipped,
            subscriptions_updated=stats.subscriptions_updated,
            workspaces_updated=stats.workspaces_updated,
        )
    else:
        stats = SeedStats(
            created=stats.created,
            updated=stats.updated + 1,
            skipped=stats.skipped,
            subscriptions_updated=stats.subscriptions_updated,
            workspaces_updated=stats.workspaces_updated,
        )

    workspaces = Workspace.objects.filter(
        is_personal=False,
        deleted__isnull=True,
    ).select_related("subscription")

    for workspace in workspaces:
        plan = _plan_for_workspace(workspace)
        if not plan:
            stats = SeedStats(
                created=stats.created,
                updated=stats.updated,
                skipped=stats.skipped + 1,
                subscriptions_updated=stats.subscriptions_updated,
                workspaces_updated=stats.workspaces_updated,
            )
            continue

        if workspace.subscription:
            target = _resolve_subscription_workspace_seat_type(plan, workspace)
            seats = max(
                1,
                (workspace.subscription.seats or 0),
                workspace.used_seats,
            )
            expected_amount = (target.monthly_credit_limit or 0) * seats
            expected_charged_amount = target.monthly_charge * seats * 100

            update_fields = []
            sub = workspace.subscription
            if sub.seats != seats:
                sub.seats = seats
                update_fields.append("seats")
            if sub.amount != expected_amount:
                sub.amount = expected_amount
                update_fields.append("amount")
            if sub.charged_amount != expected_charged_amount:
                sub.charged_amount = expected_charged_amount
                update_fields.append("charged_amount")
            if update_fields:
                sub.save(update_fields=update_fields + ["updated_at"])
                stats = SeedStats(
                    created=stats.created,
                    updated=stats.updated,
                    skipped=stats.skipped,
                    subscriptions_updated=stats.subscriptions_updated + 1,
                    workspaces_updated=stats.workspaces_updated,
                )

            # For TEAM workspaces, assign a default seat type to unassigned active members.
            if plan == PricingPlan.TEAM:
                updated_count = workspace.memberships.filter(
                    deleted__isnull=True,
                    seat_type__isnull=True,
                ).update(seat_type=target)
                if updated_count:
                    stats = SeedStats(
                        created=stats.created,
                        updated=stats.updated,
                        skipped=stats.skipped,
                        subscriptions_updated=stats.subscriptions_updated,
                        workspaces_updated=stats.workspaces_updated + 1,
                    )

    print(
        "Seeded workspace seat types:",
        f"created={stats.created}",
        f"updated={stats.updated}",
        f"skipped_workspaces={stats.skipped}",
        f"subscriptions_updated={stats.subscriptions_updated}",
        f"workspaces_updated={stats.workspaces_updated}",
    )
