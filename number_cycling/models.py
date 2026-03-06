from __future__ import annotations

from django.db import models
import phonenumber_field.modelfields
from bots.models.bot_integration import (
    Platform,
    WhatsappPhoneNumberField,
    validate_phonenumber,
)


class SharedPhoneNumberQuerySet(models.QuerySet):
    def any_active_number(
        self, platform: Platform, country_code: str = ""
    ) -> SharedPhoneNumber:
        qs = self.filter(platform=platform.value, is_active=True)
        if country_code:
            qs = qs.filter(country_code=country_code)
        obj = qs.order_by("?").first()
        if not obj:
            raise SharedPhoneNumber.DoesNotExist(
                f"Sorry, {platform.label} phone numbers are currently unavailable to assign. Please contact us or try again later."
            )
        return obj

    def available_country_codes(self, platform: Platform) -> list[str]:
        return list(
            self.filter(platform=platform.value, is_active=True)
            .exclude(country_code="")
            .values_list("country_code", flat=True)
            .distinct()
        )


class SharedPhoneNumber(models.Model):
    platform = models.IntegerField(
        choices=Platform.choices,
        help_text="The platform this phone number is for (WhatsApp, Twilio, etc.)",
    )

    wa_phone_number = WhatsappPhoneNumberField(
        blank=True,
        default="",
        help_text="Bot's WhatsApp phone number (only for display)",
        validators=[validate_phonenumber],
    )
    wa_phone_number_id = models.CharField(
        max_length=256,
        blank=True,
        default=None,
        null=True,
        unique=True,
        help_text="Bot's WhatsApp phone number id (mandatory)",
    )

    twilio_phone_number = phonenumber_field.modelfields.PhoneNumberField(
        blank=True,
        null=True,
        default=None,
        unique=True,
        help_text="Twilio phone number as found on twilio.com/console/phone-numbers/incoming (mandatory)",
    )
    twilio_phone_number_sid = models.TextField(
        blank=True,
        default="",
        help_text="Twilio phone number sid as found on twilio.com/console/phone-numbers/incoming (only for display)",
    )

    country_code = models.CharField(
        max_length=2,
        blank=True,
        default="",
        help_text="ISO 3166-1 alpha-2 country code (e.g. 'US', 'IN')",
    )

    is_active = models.BooleanField(
        default=True, help_text="Whether this phone number is available for assignment"
    )
    notes = models.TextField(
        blank=True,
        default="",
        help_text="Optional notes about this phone number",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = SharedPhoneNumberQuerySet.as_manager()

    class Meta:
        ordering = ["-updated_at"]
        get_latest_by = "updated_at"
        indexes = [
            models.Index(fields=["-updated_at"]),
            models.Index(fields=["platform", "is_active", "country_code"]),
        ]

    def __str__(self) -> str:
        return (
            (self.wa_phone_number and self.wa_phone_number.as_international)
            or self.wa_phone_number_id
            or (self.twilio_phone_number and self.twilio_phone_number.as_international)
            or self.twilio_phone_number_sid
            or self.notes
            or ""
        )


class SharedPhoneNumberBotUser(models.Model):
    shared_phone_number = models.ForeignKey(
        "number_cycling.SharedPhoneNumber",
        on_delete=models.CASCADE,
        related_name="users",
    )

    wa_phone_number = WhatsappPhoneNumberField(
        blank=True,
        null=True,
        help_text="The user's WhatsApp phone number",
        validators=[validate_phonenumber],
    )
    twilio_phone_number = phonenumber_field.modelfields.PhoneNumberField(
        blank=True,
        null=True,
        help_text="The user's Twilio phone number",
    )

    bot_integration = models.ForeignKey(
        "bots.BotIntegration",
        on_delete=models.CASCADE,
        related_name="shared_phone_number_users",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        get_latest_by = "updated_at"
        indexes = [
            models.Index(fields=["-updated_at"]),
        ]
        unique_together = [
            ("wa_phone_number", "shared_phone_number"),
            ("twilio_phone_number", "shared_phone_number"),
        ]

        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(wa_phone_number__isnull=False)
                    ^ models.Q(twilio_phone_number__isnull=False)
                ),
                name="exactly_one_of_wa_or_twilio_phone_number",
            ),
        ]

    def __str__(self):
        phone_number = (
            (self.wa_phone_number and self.wa_phone_number.as_international)
            or (self.twilio_phone_number and self.twilio_phone_number.as_international)
            or "No phone number"
        )
        return f"{phone_number} <> {self.bot_integration}"
