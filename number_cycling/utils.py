import random
from typing import Tuple

from django.db import transaction
from bots.models.bot_integration import BotIntegration, Platform
from number_cycling.models import BotExtension, ProvisionedNumber


def generate_unique_extension_number(length: int = 5) -> int:
    max_attempts = 100

    for _ in range(max_attempts):
        # Generate a random number with specified length
        # For a 5-digit number, generate between 10000-99999
        min_value = 10 ** (length - 1)
        max_value = (10**length) - 1
        extension_number = random.randint(min_value, max_value)

        # Check if this extension number already exists
        if not BotExtension.objects.filter(extension_number=extension_number).exists():
            return extension_number

    raise RuntimeError(f"Unable to generate unique {length}-digit extension number")


def create_bot_integration_with_extension(
    name: str,
    created_by,
    workspace,
    platform: Platform,
) -> Tuple[BotIntegration, BotExtension]:
    if platform != Platform.TWILIO:
        raise ValueError("Invalid platform")

    available_number = ProvisionedNumber.get_available_phone_number(platform)

    with transaction.atomic():
        bot_integration = BotIntegration.objects.create(
            name=name,
            created_by=created_by,
            workspace=workspace,
            platform=platform.value,
        )

        if platform == Platform.TWILIO:
            bot_integration.twilio_phone_number = available_number.phone_number
        bot_integration.save()

        extension_number = generate_unique_extension_number()

        extension = BotExtension.objects.create(
            bot_integration=bot_integration,
            extension_number=extension_number,
        )

        return bot_integration, extension
