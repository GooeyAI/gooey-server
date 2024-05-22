from __future__ import annotations

from datetime import datetime

from furl import furl
import requests
import stripe
from dateutil.parser import isoparse
from django.core.validators import MinValueValidator
from django.db import models

from daras_ai_v2.exceptions import raise_for_status

from .plans import PricingPlan
from .utils import (
    cancel_stripe_subscription,
    cancel_paypal_subscription,
)
from app_users.models import PaymentProvider
from daras_ai_v2 import paypal, settings


class AutoRechargeSubscription(models.Model):
    payment_provider = models.IntegerField(
        choices=PaymentProvider.choices, null=True, blank=True
    )
    external_id = models.CharField(
        max_length=255,
        help_text="Subscription ID for PayPal",
        null=True,
        blank=True,
    )
    topup_amount = models.IntegerField(validators=[MinValueValidator(1)])
    topup_threshold = models.IntegerField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def has_payment_method(self) -> bool:
        return bool(self.external_id)


class Subscription(models.Model):
    plan = models.IntegerField(choices=PricingPlan.choices())
    payment_provider = models.IntegerField(choices=PaymentProvider.choices)
    external_id = models.CharField(
        max_length=255,
        help_text="Subscription ID from the payment provider",
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
                cancel_stripe_subscription(self.external_id)
            case PaymentProvider.PAYPAL:
                cancel_paypal_subscription(self.external_id)
            case _:
                raise NotImplementedError(
                    f"Can't cancel subscription for {self.payment_provider}"
                )

    def get_next_invoice_date(self) -> datetime:
        if self.payment_provider == PaymentProvider.STRIPE:
            subscription = stripe.Subscription.retrieve(self.external_id)
            period_end = subscription.current_period_end
            return datetime.fromtimestamp(period_end)
        elif self.payment_provider == PaymentProvider.PAYPAL:
            r = requests.get(
                str(
                    furl(settings.PAYPAL_BASE)
                    .add(path=f"/v1/billing/subscriptions/{self.external_id}")
                    .url
                ),
                headers={"Authorization": paypal.generate_auth_header()},
            )
            raise_for_status(r)
            subscription = r.json()
            print(f"{subscription=}")
            period_end = subscription["billing_info"]["next_billing_time"]
            return isoparse(period_end)
        else:
            raise ValueError("Invalid Payment Provider")

    def get_default_payment_method_preview(self) -> str | None:
        match self.payment_provider:
            case PaymentProvider.STRIPE:
                subscription = stripe.Subscription.retrieve(
                    self.external_id, expand=["default_payment_method"]
                )
                source = subscription.default_payment_method
                if not source:
                    return None
                match source.type:
                    case "card":
                        return f"{source.card.brand} ending in {source.card.last4}"
                    case other_method:
                        return other_method
            case PaymentProvider.PAYPAL:
                subscription = paypal.Subscription.retrieve(self.external_id)
                ...
            case _:
                raise NotImplementedError(
                    f"Can't get payment method preview for {self.payment_provider}"
                )

    class Meta:
        unique_together = ("payment_provider", "external_id")
        indexes = [
            models.Index(fields=["plan"]),
        ]
