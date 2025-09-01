from django.db import transaction, IntegrityError
from bots.models.bot_integration import BotIntegration, Platform
from number_cycling.models import BotExtension, ProvisionedNumber
from daras_ai_v2 import settings
import hashids
import re


extension_hashids = hashids.Hashids(
    salt=settings.HASHIDS_API_SALT + "EXTENSIONS", min_length=3
)


def create_bot_integration_with_extension(
    name: str,
    created_by,
    workspace,
    platform: Platform,
) -> BotIntegration:
    if platform != Platform.TWILIO and platform != Platform.WHATSAPP:
        raise ValueError("Invalid platform")

    with transaction.atomic():
        available_number = ProvisionedNumber.get_available_phone_number(platform)

        bot_integration = BotIntegration.objects.create(
            name=name,
            created_by=created_by,
            workspace=workspace,
            platform=platform.value,
        )

        if platform == Platform.TWILIO:
            bot_integration.twilio_phone_number = available_number.phone_number
        elif platform == Platform.WHATSAPP:
            bot_integration.wa_phone_number_id = available_number.wa_phone_number_id
            bot_integration.wa_phone_number = available_number.phone_number

        bot_integration.save()

        for _ in range(5):
            extension_number = generate_unique_extension_number(bot_integration, 5)
            try:
                BotExtension.objects.create(
                    bot_integration=bot_integration,
                    extension_number=extension_number,
                )
                return bot_integration
            except IntegrityError:
                # Retry with a different generated number
                continue

        raise RuntimeError("Unable to create unique 5-digit extension number")


def generate_unique_extension_number(
    bot_integration: BotIntegration, length: int = 5
) -> int:
    """
    Generate a unique extension number candidate for a bot integration.
    """
    seed = bot_integration.id
    for attempt in range(5):
        seed = seed + attempt
        hashid = extension_hashids.encode(seed)
        extension_number = (10 ** (length - 1)) + (
            abs(hash(hashid)) % (10 ** (length - 1))
        )

        if not BotExtension.objects.filter(extension_number=extension_number).exists():
            return extension_number

    raise RuntimeError(f"Unable to generate unique {length}-digit extension number")


def get_extension_number(message_text: str) -> int | None:
    if not message_text:
        return None

    message_text = message_text.strip().lower()

    # Pattern to match extension formats that start with slash
    patterns = [
        r"^/(?:extension|ext)\s+(\d{5})$",  # "/extension 12345" or "/ext 12345"
        r"\b(\d{5})\b",  # any standalone 5-digit number in the message
    ]

    for pattern in patterns:
        match = re.search(pattern, message_text)
        if match:
            return int(match.group(1))

    return None
