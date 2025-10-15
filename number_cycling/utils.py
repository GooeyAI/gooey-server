import random
import re

import hashids
from django.db import IntegrityError, transaction

from bots.models.bot_integration import BotIntegration, Platform
from daras_ai_v2 import settings
from number_cycling.models import SharedPhoneNumber, SharedPhoneNumberBotUser
from workspaces.models import Workspace
import secrets


def create_bot_integration_with_extension(
    name: str,
    created_by,
    workspace: Workspace,
    platform: Platform,
) -> BotIntegration:
    if platform != Platform.TWILIO and platform != Platform.WHATSAPP:
        raise ValueError("Invalid platform")

    with transaction.atomic():
        shared_phone_number = SharedPhoneNumber.objects.any_active_number(platform)
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
    match = re.search(r"\b(\d{5})\b", message_text)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    else:
        return None
