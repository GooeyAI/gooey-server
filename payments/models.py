from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import stripe
from django.db import models
from furl import furl

from app_users.models import PaymentProvider
from daras_ai_v2 import paypal, settings
from .plans import PricingPlan, stripe_get_addon_product


@dataclass
class PaymentMethodSummary:
    payment_method_type: str | None = None
    card_brand: str | None = None
    card_last4: str | None = None
    billing_email: str | None = None


class SubscriptionQuerySet(models.QuerySet):
    def get_by_paypal_subscription_id(self, subscription_id: str) -> Subscription:
        return super().get(
            payment_provider=PaymentProvider.PAYPAL, external_id=subscription_id
        )

    def get_by_stripe_subscription_id(self, subscription_id: str) -> Subscription:
        return super().get(
            payment_provider=PaymentProvider.STRIPE, external_id=subscription_id
        )


class Subscription(models.Model):
    plan = models.IntegerField(choices=PricingPlan.db_choices())
    payment_provider = models.IntegerField(
        choices=PaymentProvider.choices, blank=True, null=True, default=None
    )
    external_id = models.CharField(
        max_length=255,
        help_text="Subscription ID from the payment provider",
        null=True,
        blank=True,
    )
    auto_recharge_enabled = models.BooleanField(default=True)
    auto_recharge_balance_threshold = models.IntegerField()
    auto_recharge_topup_amount = models.IntegerField(
        default=settings.ADDON_AMOUNT_CHOICES[0],
    )
    monthly_spending_budget = models.IntegerField(
        null=True,
        blank=True,
        help_text="In USD, pause auto-recharge just before the spending exceeds this amount in a calendar month",
    )
    monthly_spending_notification_threshold = models.IntegerField(
        null=True,
        blank=True,
        help_text="In USD, send an email when spending crosses this threshold in a calendar month",
    )

    monthly_spending_notification_sent_at = models.DateTimeField(null=True, blank=True)
    monthly_budget_email_sent_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = SubscriptionQuerySet.as_manager()

    class Meta:
        unique_together = ("payment_provider", "external_id")
        indexes = [
            models.Index(fields=["plan"]),
        ]

    def __str__(self):
        return PricingPlan.from_sub(self).title

    def full_clean(self, *args, **kwargs):
        if self.plan and self.auto_recharge_enabled:
            if not self.auto_recharge_balance_threshold:
                self.auto_recharge_balance_threshold = (
                    self._get_default_auto_recharge_balance_threshold()
                )

            if not self.monthly_spending_budget:
                self.monthly_spending_budget = (
                    self._get_default_monthly_spending_budget()
                )

            if not self.monthly_spending_notification_threshold:
                self.monthly_spending_notification_threshold = (
                    self._get_default_monthly_spending_notification_threshold()
                )

        return super().full_clean(*args, **kwargs)

    def _get_default_auto_recharge_balance_threshold(self):
        # 25% of the monthly credit subscription
        threshold = int(PricingPlan.from_sub(self).credits * 0.25)
        return nearest_choice(
            settings.AUTO_RECHARGE_BALANCE_THRESHOLD_CHOICES, threshold
        )

    def _get_default_monthly_spending_budget(self):
        # 3x the monthly subscription charge
        return 3 * PricingPlan.from_sub(self).monthly_charge

    def _get_default_monthly_spending_notification_threshold(self):
        # 80% of the monthly budget
        return int(0.8 * self._get_default_monthly_spending_budget())

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
            return (
                datetime.fromtimestamp(period_end, tz=timezone.utc)
                if period_end
                else None
            )
        elif self.payment_provider == PaymentProvider.PAYPAL:
            subscription = paypal.Subscription.retrieve(self.external_id)
            return (
                subscription.billing_info.next_billing_time
                if subscription.billing_info
                else None
            )
        else:
            raise ValueError("Invalid Payment Provider")

    def get_payment_method_summary(self) -> PaymentMethodSummary:
        summary = PaymentMethodSummary()
        match self.payment_provider:
            case PaymentProvider.STRIPE:
                pm = self.stripe_get_default_payment_method()
                if pm:
                    summary.payment_method_type = pm.type
                    summary.card_brand = pm.card and pm.card.brand
                    summary.card_last4 = pm.card and pm.card.last4
                    summary.billing_email = (
                        pm.billing_details and pm.billing_details.email
                    )
            case PaymentProvider.PAYPAL:
                subscription = paypal.Subscription.retrieve(self.external_id)
                subscriber = subscription.subscriber
                if subscriber and subscriber.payment_source:
                    summary.payment_method_type = "card"
                    summary.card_brand = subscriber.payment_source.get("card", {}).get(
                        "brand"
                    )
                    summary.card_last4 = subscriber.payment_source.get("card", {}).get(
                        "last_digits"
                    )
                if subscriber and subscriber.email_address:
                    summary.billing_email = subscriber.email_address

        return summary

    def stripe_get_default_payment_method(self) -> stripe.PaymentMethod | None:
        if self.payment_provider != PaymentProvider.STRIPE:
            raise ValueError("Invalid Payment Provider")

        subscription = stripe.Subscription.retrieve(self.external_id)
        if subscription.default_payment_method:
            return stripe.PaymentMethod.retrieve(subscription.default_payment_method)

        customer = stripe.Customer.retrieve(subscription.customer)
        if customer.invoice_settings.default_payment_method:
            return stripe.PaymentMethod.retrieve(
                customer.invoice_settings.default_payment_method
            )

        return None

    def stripe_get_or_create_auto_invoice(
        self,
        amount_in_dollars: int,
        metadata_key: str,
    ) -> stripe.Invoice:
        """
        Fetches the relevant invoice, or creates one if it doesn't exist.

        This is the fallback order:
        - Fetch an open invoice with metadata_key in the metadata
        - Fetch a $metadata_key invoice that was recently paid
        - Create an invoice with amount=amount_in_dollars and $metadata_key
        """
        customer_id = self.stripe_get_customer_id()
        invoices = stripe.Invoice.list(
            customer=customer_id,
            collection_method="charge_automatically",
        )
        invoices = [inv for inv in invoices.data if metadata_key in inv.metadata]

        open_invoice = next((inv for inv in invoices if inv.status == "open"), None)
        if open_invoice:
            return open_invoice

        recently_paid_invoice = next(
            (
                inv
                for inv in invoices
                if inv.status == "paid"
                and datetime.now(tz=timezone.utc).timestamp() - inv.created
                < settings.AUTO_RECHARGE_COOLDOWN_SECONDS
            ),
            None,
        )
        if recently_paid_invoice:
            return recently_paid_invoice

        return self.stripe_create_auto_invoice(
            amount_in_dollars=amount_in_dollars, metadata_key=metadata_key
        )

    def stripe_create_auto_invoice(self, *, amount_in_dollars: int, metadata_key: str):
        customer_id = self.stripe_get_customer_id()
        invoice = stripe.Invoice.create(
            customer=customer_id,
            collection_method="charge_automatically",
            metadata={metadata_key: True},
            auto_advance=False,
            pending_invoice_items_behavior="exclude",
        )
        stripe.InvoiceItem.create(
            customer=customer_id,
            invoice=invoice,
            price_data={
                "currency": "usd",
                "product": stripe_get_addon_product().id,
                "unit_amount_decimal": (
                    settings.ADDON_CREDITS_PER_DOLLAR / 100
                ),  # in cents
            },
            quantity=amount_in_dollars * settings.ADDON_CREDITS_PER_DOLLAR,
            currency="usd",
            metadata={metadata_key: True},
        )
        invoice.finalize_invoice(auto_advance=True)
        return invoice

    def stripe_get_customer_id(self) -> str:
        if self.payment_provider == PaymentProvider.STRIPE:
            subscription = stripe.Subscription.retrieve(self.external_id)
            return subscription.customer
        raise ValueError("Invalid Payment Provider")

    def stripe_attempt_addon_purchase(self, amount_in_dollars: int) -> bool:
        invoice = self.stripe_create_auto_invoice(
            amount_in_dollars=amount_in_dollars,
            metadata_key="addon",
        )
        if invoice.status == "open":
            pm = self.stripe_get_default_payment_method()
            invoice.pay(payment_method=pm)
            return True
        return False

    def get_external_management_url(self) -> str:
        """
        Get URL to Stripe/PayPal for user to manage the subscription.
        """
        match self.payment_provider:
            case PaymentProvider.STRIPE:
                portal = stripe.billing_portal.Session.create(
                    customer=self.stripe_get_customer_id(),
                    return_url=str(furl(settings.APP_BASE_URL) / "account" / ""),
                )
                return portal.url
            case PaymentProvider.PAYPAL:
                return str(
                    settings.PAYPAL_WEB_BASE_URL
                    / "myaccount"
                    / "autopay"
                    / "connect"
                    / self.external_id
                )
            case _:
                raise NotImplementedError(
                    f"Can't get management URL for subscription with provider {self.payment_provider}"
                )

    def has_sent_monthly_spending_notification_this_month(self) -> bool:
        return self.monthly_spending_notification_sent_at and (
            self.monthly_spending_notification_sent_at.strftime("%B %Y")
            == datetime.now(tz=timezone.utc).strftime("%B %Y")
        )

    def has_sent_monthly_budget_email_this_month(self) -> bool:
        return self.monthly_budget_email_sent_at and (
            self.monthly_budget_email_sent_at.strftime("%B %Y")
            == datetime.now(tz=timezone.utc).strftime("%B %Y")
        )

    def should_send_monthly_spending_notification(self) -> bool:
        assert self.has_user

        return bool(
            self.monthly_spending_notification_threshold
            and not self.has_sent_monthly_spending_notification_this_month()
            and self.user.get_dollars_spent_this_month()
            >= self.monthly_spending_notification_threshold
        )


def nearest_choice(choices: list[int], value: int) -> int:
    # nearest value in choices that is less than or equal to value
    return min(filter(lambda x: x <= value, choices), key=lambda x: abs(x - value))
