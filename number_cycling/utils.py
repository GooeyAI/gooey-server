import random
from typing import Tuple
from django.db import transaction, IntegrityError
from bots.models.bot_integration import BotIntegration, Platform
from number_cycling.models import BotExtension, ProvisionedNumber
from daras_ai_v2 import settings
import hashids

extension_hashids = hashids.Hashids(
    salt=settings.HASHIDS_API_SALT + "EXTENSIONS", min_length=3
)


def generate_unique_extension_number(
    bot_integration: BotIntegration, length: int = 5
) -> int:
    """
    Generate a unique extension number for a bot integration.
    """
    seed = bot_integration.id
    for attempt in range(5):
        seed = seed + attempt
        hashid = extension_hashids.encode(seed)
        extension_number = (10 ** (length - 1)) + (
            abs(hash(hashid)) % (10 ** (length - 1))
        )

        try:
            with transaction.atomic():
                if not BotExtension.objects.filter(
                    extension_number=extension_number
                ).exists():
                    return extension_number
        except IntegrityError:
            continue

    raise RuntimeError(f"Unable to generate unique {length}-digit extension number")


def create_bot_integration_with_extension(
    name: str,
    created_by,
    workspace,
    platform: Platform,
) -> Tuple[BotIntegration, BotExtension]:
    if platform != Platform.TWILIO:
        raise ValueError("Invalid platform")

    with transaction.atomic():
        available_number = ProvisionedNumber.get_available_phone_number(platform)

        bot_integration = BotIntegration.objects.create(
            name=name,
            created_by=created_by,
            workspace=workspace,
            platform=platform.value,
        )
        bot_integration.twilio_phone_number = available_number.phone_number
        bot_integration.save()

        extension_number = generate_unique_extension_number(bot_integration, 5)

        extension = BotExtension.objects.create(
            bot_integration=bot_integration,
            extension_number=extension_number,
        )

        return bot_integration, extension
