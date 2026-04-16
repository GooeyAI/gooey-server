from __future__ import annotations

from dataclasses import dataclass


from payments.models import SeatType
from payments.plans import PricingPlan

DEFAULT_PLAN_SEAT_TYPES: dict[PricingPlan, list[dict[str, int]]] = {
    PricingPlan.PRO: [
        {"monthly_charge": 25, "monthly_credit_limit": 2_000},
        {"monthly_charge": 50, "monthly_credit_limit": 4_200},
        {"monthly_charge": 100, "monthly_credit_limit": 9_000},
        {"monthly_charge": 200, "monthly_credit_limit": 20_000},
    ],
    PricingPlan.TEAM: [
        {"name": "Starter", "monthly_charge": 40, "monthly_credit_limit": 2_500},
        {"name": "Advanced", "monthly_charge": 100, "monthly_credit_limit": 7_500},
        {"name": "Researcher", "monthly_charge": 200, "monthly_credit_limit": 20_000},
    ],
}


@dataclass(frozen=True)
class SeedStats:
    created: int = 0
    updated: int = 0


def _default_seat_type_name(*, monthly_credit_limit: int) -> str:
    return f"{monthly_credit_limit:,} credits/month"


def run(*_args):
    stats = SeedStats()

    # seed global seat types (shared across workspaces)
    for plan, seat_types in DEFAULT_PLAN_SEAT_TYPES.items():
        for seat_type in seat_types:
            key = seat_type.get(
                "key", f"2026/{plan.key}/{seat_type['monthly_credit_limit']}"
            )
            name = seat_type.get(
                "name",
                _default_seat_type_name(
                    monthly_credit_limit=seat_type["monthly_credit_limit"]
                ),
            )
            _, created = SeatType.objects.update_or_create(
                key=key,
                plan=plan.db_value,
                defaults=dict(
                    name=name,
                    monthly_charge=seat_type["monthly_charge"],
                    monthly_credit_limit=seat_type["monthly_credit_limit"],
                    is_public=True,
                ),
            )
            if created:
                stats = SeedStats(created=stats.created + 1, updated=stats.updated)
            else:
                stats = SeedStats(created=stats.created, updated=stats.updated + 1)

    _, admin_created = SeatType.objects.get_or_create_gooey_admin_seat_type()
    if admin_created:
        stats = SeedStats(created=stats.created + 1, updated=stats.updated)
    else:
        stats = SeedStats(created=stats.created, updated=stats.updated + 1)

    print(
        "Seeded workspace seat types:",
        f"created={stats.created}",
        f"updated={stats.updated}",
    )
