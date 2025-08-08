from __future__ import annotations

import math
import typing
import uuid

from django.conf import settings
from django.db import transaction
from django.db.models import F, TextChoices, Sum

from app_users.models import AppUser
from bots.models import Platform, SavedRun
from usage_costs.cost_utils import create_usage_cost, get_model_pricing

if typing.TYPE_CHECKING:
    from usage_costs.models import ModelPricing


class IVRPlatformMedium(TextChoices):
    twilio_voice = "TWILIO_VOICE", "Twilio Voice"
    twilio_sms = "TWILIO_SMS", "Twilio SMS"


IVR_CREDITS_PRICE_MULTIPLIER = 1.5


def record_twilio_voice_call_cost(data: dict):
    from usage_costs.models import ModelSku

    quantity = int((data.get("DialCallDuration") or data["CallDuration"])[0])
    if quantity <= 0:
        return
    call_sid = data["CallSid"][0]
    dial_call_sid = data.get("DialCallSid", [call_sid])[0]

    try:
        sr = SavedRun.objects.get(platform=Platform.TWILIO, user_message_id=call_sid)
    except SavedRun.DoesNotExist:
        return

    pricing = get_model_pricing(
        model_id=IVRPlatformMedium.twilio_voice.value,
        sku=ModelSku.ivr_call,
    )

    unit_cost = get_twilio_voice_unit_cost(dial_call_sid) or pricing.unit_cost

    create_usage_cost_and_deduct_credits(sr, pricing, quantity, unit_cost)


@transaction.atomic
def create_usage_cost_and_deduct_credits(
    sr: SavedRun, pricing: ModelPricing, quantity: int, unit_cost: float
):
    usage_cost = create_usage_cost(
        sr=sr,
        pricing=pricing,
        quantity=quantity,
        unit_cost=unit_cost,
        unit_quantity=pricing.unit_quantity,
    )
    if not sr.transaction_id:
        # credits have not yet been deducted
        return
    # credits for the run have already been deducted; we have to deduct more
    amount = ivr_dollar_to_credits(usage_cost.dollar_amount)
    sr.workspace.add_balance_raw(
        amount=-amount,
        invoice_id=f"gooey_in_{uuid.uuid1()}",
        user=AppUser.objects.get(uid=sr.uid),
    )
    SavedRun.objects.filter(id=sr.id).update(price=F("price") + amount)


def get_twilio_voice_unit_cost(call_sid: str) -> float:
    import twilio.rest

    client = twilio.rest.Client(
        account_sid=settings.TWILIO_ACCOUNT_SID,
        username=settings.TWILIO_API_KEY_SID,
        password=settings.TWILIO_API_KEY_SECRET,
    )
    call = client.calls(call_sid).fetch()
    number_pricing = client.pricing.v2.voice.numbers(call.to).fetch()
    if call.direction == "inbound":
        return float(number_pricing.inbound_call_price["base_price"])
    else:
        return float(number_pricing.outbound_call_prices[0]["base_price"])


def get_ivr_price_credits_and_seconds(sr: SavedRun) -> tuple[int, float]:
    """
    Return a tuple of (credits, duration_seconds) for IVR usage.
    """
    from usage_costs.models import ModelSku

    qs = sr.usage_costs.filter(
        pricing__model_id=IVRPlatformMedium.twilio_voice.value,
        pricing__sku=ModelSku.ivr_call,
    )
    credits = 0
    seconds = 0
    # need to loop instead of sql aggregate because of ceil() on every individual cost component
    for usage_cost in qs:
        credits += ivr_dollar_to_credits(usage_cost.dollar_amount)
        seconds += usage_cost.quantity
    return credits, seconds


def ivr_dollar_to_credits(dollar_amount) -> int:
    return math.ceil(
        float(dollar_amount)
        * settings.ADDON_CREDITS_PER_DOLLAR
        * IVR_CREDITS_PRICE_MULTIPLIER
    )


def get_non_ivr_price_credits(sr: SavedRun, default: int = 1):
    from usage_costs.models import ModelSku

    qs = sr.usage_costs.exclude(
        pricing__model_id=IVRPlatformMedium.twilio_voice.value,
        pricing__sku=ModelSku.ivr_call,
    )
    dollar_amount = qs.aggregate(total=Sum("dollar_amount"))["total"]
    if not dollar_amount:
        return default
    return dollar_amount * settings.ADDON_CREDITS_PER_DOLLAR
