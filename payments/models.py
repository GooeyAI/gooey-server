from dataclasses import dataclass
from enum import Enum

from django.db import models

from .utils import make_stripe_recurring_plan, make_paypal_recurring_plan
from app_users.models import PaymentProvider
from daras_ai_v2 import settings


@dataclass
class PricingData:
    key: str
    display_name: str
    title: str
    description: str
    stripe: dict | None = None
    paypal: dict | None = None


class PricingPlan(PricingData, Enum):
    BASIC = (
        1,
        {
            "key": "basic",
            "display_name": "Basic Plan",
            "title": "$10/month",
            "description": "Buy a monthly plan for $10 and get new 1500 credits (~300 runs) every month.",
            "stripe": make_stripe_recurring_plan(
                product_name="Gooey.AI Basic Plan", credits=1_500, amount=10
            ),
            "paypal": make_paypal_recurring_plan(
                plan_id=settings.PAYPAL_PLAN_IDS["basic"], credits=1_500, amount=10
            ),
        },
    )
    PREMIUM = (
        2,
        {
            "key": "premium",
            "display_name": "Premium Plan",
            "title": "$50/month + Bots",
            "description": "10000 Credits (~2000 runs) for $50/month. Includes special access to build bespoke, embeddable [videobots](/video-bots/)",
            "stripe": make_stripe_recurring_plan(
                product_name="Gooey.AI Premium Plan", credits=10_000, amount=50
            ),
            "paypal": make_paypal_recurring_plan(
                plan_id=settings.PAYPAL_PLAN_IDS["premium"], credits=10_000, amount=50
            ),
        },
    )

    def __init__(self, value: int, data: dict):
        PricingData.__init__(self, **data)
        self._value_ = value

    @classmethod
    def choices(cls):
        return {plan.value: plan.name for plan in cls}


class AutoRechargeSubscription(models.Model):
    payment_provider = models.IntegerField(choices=PaymentProvider.choices)
    external_id = models.CharField(
        max_length=255,
        help_text="Subscription ID for PayPal and payment_method_id for Stripe",
    )
    topup_amount = models.IntegerField()
    topup_threshold = models.IntegerField()
