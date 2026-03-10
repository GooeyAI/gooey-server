import random
import re

import hashids
import phonenumbers
from django.db import IntegrityError, transaction

from bots.models.bot_integration import BotIntegration, Platform
from daras_ai_v2 import settings
from number_cycling.models import SharedPhoneNumber, SharedPhoneNumberBotUser
from workspaces.models import Workspace
import secrets

EXTENSION_NUMBER_LENGTH = 5


REGIONAL_INDICATOR_A = ord("🇦")  # U+1F1E6
ASCII_A = ord("A")


def country_code_label(country_code: str) -> str:
    """Derive a display label from an ISO 3166-1 alpha-2 country code.

    e.g. "US" → "🇺🇸 US +1", "IN" → "🇮🇳 IN +91"
    """
    cc = country_code.upper()
    flag = "".join(chr(REGIONAL_INDICATOR_A + (ord(ch) - ASCII_A)) for ch in cc)
    dial_code = phonenumbers.country_code_for_region(cc)
    if not dial_code:
        return f"{flag} {cc}"
    return f"{flag} {cc} +{dial_code}"


def create_bot_integration_with_extension(
    name: str,
    created_by,
    workspace: Workspace,
    platform: Platform,
    country_code: str = "",
) -> BotIntegration:
    if platform != Platform.TWILIO and platform != Platform.WHATSAPP:
        raise ValueError("Invalid platform")

    with transaction.atomic():
        shared_phone_number = SharedPhoneNumber.objects.any_active_number(
            platform, country_code=country_code
        )
        for _ in range(10):
            try:
                return BotIntegration.objects.create(
                    name=name,
                    created_by=created_by,
                    workspace=workspace,
                    platform=platform.value,
                    wa_phone_number_id=shared_phone_number.wa_phone_number_id,
                    wa_phone_number=shared_phone_number.wa_phone_number,
                    twilio_phone_number=shared_phone_number.twilio_phone_number,
                    twilio_phone_number_sid=shared_phone_number.twilio_phone_number_sid,
                    shared_phone_number=shared_phone_number,
                    extension_number=10_000 + secrets.randbelow(90_000),
                )
            except IntegrityError:
                # Retry with a different generated number
                continue
        raise RuntimeError("Unable to create unique 5-digit extension number")


def parse_extension_number(message_text: str) -> int | None:
    if not message_text:
        return None
    match = re.search(r"\b(\d{%d})\b" % EXTENSION_NUMBER_LENGTH, message_text)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    else:
        return None
