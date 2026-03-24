from __future__ import annotations

from dataclasses import dataclass

from django.utils import timezone

from payments.models import SeatType
from payments.plans import PricingPlan

GOOEY_ADMIN_SEAT_TYPE_NAME = "Gooey Admin"
DEFAULT_PLAN_SEAT_TYPES: dict[PricingPlan, list[dict[str, int]]] = {
    PricingPlan.PRO: [
        {"monthly_charge": 25, "monthly_credit_limit": 2_000},
        {"monthly_charge": 50, "monthly_credit_limit": 4_200},
        {"monthly_charge": 100, "monthly_credit_limit": 9_000},
        {"monthly_charge": 200, "monthly_credit_limit": 20_000},
        {"monthly_charge": 300, "monthly_credit_limit": 32_000},
        {"monthly_charge": 400, "monthly_credit_limit": 44_000},
    ],
    PricingPlan.TEAM: [
        {"name": "Starter", "monthly_charge": 40, "monthly_credit_limit": 2_500},
        {"name": "Learner", "monthly_charge": 60, "monthly_credit_limit": 5_000},
        {"name": "Researcher", "monthly_charge": 110, "monthly_credit_limit": 9_000},
        {"monthly_charge": 200, "monthly_credit_limit": 20_000},
        {"monthly_charge": 300, "monthly_credit_limit": 32_000},
        {"monthly_charge": 400, "monthly_credit_limit": 44_000},
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

    current_year = timezone.now().year

    # seed global seat types (shared across workspaces)
    for plan, seat_types in DEFAULT_PLAN_SEAT_TYPES.items():
        for seat_type in seat_types:
            key = seat_type.get(
                "key", f"{current_year}/{plan.key}/{seat_type['monthly_credit_limit']}"
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
                stats = SeedStats(
                    created=stats.created + 1,
                    updated=stats.updated,
                )
            else:
                stats = SeedStats(
                    created=stats.created,
                    updated=stats.updated + 1,
                )

    _, admin_created = SeatType.objects.update_or_create(
        name=GOOEY_ADMIN_SEAT_TYPE_NAME,
        key=f"{current_year}/{PricingPlan.TEAM.key}/gooey-admin",
        defaults=dict(
            monthly_charge=0,
            monthly_credit_limit=2_500,
            is_public=False,
            plan=PricingPlan.TEAM.db_value,
        ),
    )
    if admin_created:
        stats = SeedStats(
            created=stats.created + 1,
            updated=stats.updated,
        )
    else:
        stats = SeedStats(
            created=stats.created,
            updated=stats.updated + 1,
        )

    print(
        "Seeded workspace seat types:",
        f"created={stats.created}",
        f"updated={stats.updated}",
    )
