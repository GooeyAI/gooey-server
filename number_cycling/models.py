from __future__ import annotations

from django.db import models
import phonenumber_field.modelfields
import random
from daras_ai_v2.exceptions import UnavailableProvisionedNumber
from bots.models.bot_integration import (
    Platform,
    WhatsappPhoneNumberField,
    validate_phonenumber,
)


class BotExtension(models.Model):
    bot_integration = models.ForeignKey(
        "bots.BotIntegration",
        on_delete=models.CASCADE,
        related_name="extensions",
        help_text="The bot integration this extension belongs to",
    )
    extension_number = models.IntegerField(
        unique=True,
        help_text="Extension number for provisioned numbers",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["extension_number"], name="bots_botext_extensi_7ea998_idx"
            ),
        ]
        unique_together = (("bot_integration", "extension_number"),)

    def __str__(self) -> str:
        return f"{self.extension_number} ({self.bot_integration})"


class BotExtensionUser(models.Model):
    extension = models.ForeignKey(
        "number_cycling.BotExtension",
        on_delete=models.CASCADE,
        related_name="bot_extension_users",
        help_text="The extension this user is associated with",
    )
    wa_phone_number = WhatsappPhoneNumberField(
        blank=True,
        null=True,
        max_length=128,
        help_text="WhatsApp phone number associated with this extension user",
        validators=[validate_phonenumber],
    )
    twilio_phone_number = phonenumber_field.modelfields.PhoneNumberField(
        blank=True,
        null=True,
        help_text="Twilio phone number associated with this extension user",
        validators=[validate_phonenumber],
        max_length=128,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["wa_phone_number"], name="bots_botext_wa_phon_7efc3f_idx"
            ),
            models.Index(
                fields=["twilio_phone_number"], name="bots_botext_twilio__e2d976_idx"
            ),
        ]
        unique_together = (
            ("extension", "twilio_phone_number"),
            ("extension", "wa_phone_number"),
        )
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(wa_phone_number__isnull=False)
                    | models.Q(twilio_phone_number__isnull=False)
                ),
                name="wa_phone_number_or_twilio_phone_number",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.extension} - "
            f"{(self.wa_phone_number and self.wa_phone_number.as_e164) or ''} "
            f"{(self.twilio_phone_number and self.twilio_phone_number.as_e164) or ''}"
        ).strip()


class ProvisionedNumber(models.Model):
    phone_number = models.CharField(
        max_length=20,
        unique=True,
        help_text="The phone number (e.g., +15551234567)",
    )

    wa_phone_number_id = models.CharField(
        max_length=256,
        blank=True,
        default=None,
        null=True,
        unique=True,
        help_text="Bot's WhatsApp phone number id (mandatory)",
    )

    platform = models.IntegerField(
        choices=Platform.choices,
        help_text="The platform this phone number is for (WhatsApp, Twilio, etc.)",
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

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["platform"], name="bots_provis_platfor_b162e3_idx"),
            models.Index(fields=["is_active"], name="bots_provis_is_acti_aedbef_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(platform=Platform.WHATSAPP)
                    | models.Q(platform=Platform.TWILIO)
                ),
                name="platform_whatsapp_or_platform_twilio",
            ),
            models.CheckConstraint(
                check=(
                    ~models.Q(platform=Platform.WHATSAPP)
                    | (
                        models.Q(phone_number__isnull=False)
                        & models.Q(wa_phone_number_id__isnull=False)
                    )
                ),
                name="wa_phone_number_and_wa_phone_number_id",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.phone_number} ({Platform(self.platform).label})"

    @classmethod
    def get_available_phone_number(cls, platform: Platform) -> ProvisionedNumber:
        available_numbers = list(
            ProvisionedNumber.objects.filter(platform=platform.value, is_active=True)
        )

        if available_numbers:
            return random.choice(available_numbers)

        raise UnavailableProvisionedNumber(
            f"Sorry, {platform.label} phone numbers are currently unavailable to assign. Please contact us or try again later."
        )
