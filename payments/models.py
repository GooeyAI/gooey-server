from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TypeVar

import stripe
from django.db import models

from .plans import PricingPlan
from app_users.models import PaymentProvider
from daras_ai_v2 import paypal, settings


T = TypeVar("T")


def is_in_list_validator(valid_values: list[T]):
    def validator(value: T):
        if value not in valid_values:
            raise ValueError(f"{value} not in {valid_values}")

    return validator


@dataclass
class PaymentMethodSummary:
    payment_method_type: str
    card_brand: str | None
    card_last4: str | None
    billing_email: str | None


class Subscription(models.Model):
    plan = models.IntegerField(choices=PricingPlan.choices())
    payment_provider = models.IntegerField(choices=PaymentProvider.choices)
    external_id = models.CharField(
        max_length=255,
        help_text="Subscription ID from the payment provider",
    )
    auto_recharge_enabled = models.BooleanField(default=False)
    auto_recharge_balance_threshold = models.IntegerField(
        validators=[
            is_in_list_validator(settings.AUTO_RECHARGE_BALANCE_THRESHOLD_CHOICES),
        ],
        null=True,
        blank=True,
    )
    auto_recharge_topup_amount = models.IntegerField(
        validators=[is_in_list_validator(settings.ADDON_AMOUNT_CHOICES)],
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def has_user(self) -> bool:
        try:
            self.user
        except Subscription.user.RelatedObjectDoesNotExist:
            return False
        else:
            return True

    def cancel(self):
        match self.payment_provider:
            case PaymentProvider.STRIPE:
                stripe.Subscription.cancel(self.external_id)
            case PaymentProvider.PAYPAL:
                paypal.Subscription.retrieve(self.external_id).cancel()
            case _:
                raise NotImplementedError(
                    f"Can't cancel subscription for {self.payment_provider}"
                )

    def get_next_invoice_date(self) -> datetime | None:
        if self.payment_provider == PaymentProvider.STRIPE:
            subscription = stripe.Subscription.retrieve(self.external_id)
            period_end = subscription.current_period_end
            return datetime.fromtimestamp(period_end) if period_end else None
        elif self.payment_provider == PaymentProvider.PAYPAL:
            subscription = paypal.Subscription.retrieve(self.external_id)
            return (
                subscription.billing_info.next_billing_time
                if subscription.billing_info
                else None
            )
        else:
            raise ValueError("Invalid Payment Provider")

    def get_payment_method_summary(self) -> PaymentMethodSummary | None:
        match self.payment_provider:
            case PaymentProvider.STRIPE:
                subscription = stripe.Subscription.retrieve(
                    self.external_id, expand=["default_payment_method"]
                )
                pm = subscription.default_payment_method
                return PaymentMethodSummary(
                    payment_method_type=pm.type,
                    card_brand=pm.card and pm.card.brand,
                    card_last4=pm.card and pm.card.last4,
                    billing_email=pm.billing_details and pm.billing_details.email,
                )
            case PaymentProvider.PAYPAL:
                subscription = paypal.Subscription.retrieve(self.external_id)
                subscriber = subscription.subscriber
                if not subscriber or not subscriber.payment_source:
                    return None
                try:
                    return PaymentMethodSummary(
                        payment_method_type="card",
                        card_brand=subscriber.payment_source["card"]["brand"],
                        card_last4=subscriber.payment_source["card"]["last_digits"],
                        billing_email=subscriber.email_address,
                    )
                except KeyError:
                    return None

    class Meta:
        unique_together = ("payment_provider", "external_id")
        indexes = [
            models.Index(fields=["plan"]),
        ]
