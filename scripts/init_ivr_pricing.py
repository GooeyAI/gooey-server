from usage_costs.models import ModelProvider, ModelSku, ModelPricing, ModelCategory
from daras_ai_v2.twilio_bot import IVRPlatformMedium

category = ModelCategory.IVR


def run():
    ivr_pricing_create(
        model_id=IVRPlatformMedium.twilio_voice.value,
        model_name=IVRPlatformMedium.twilio_voice.label,
        unit_cost=1,
        unit_quantity=1,
        provider=ModelProvider.twilio,
        pricing_url="https://www.twilio.com/en-us/voice/pricing/us",
        notes="Twilio Voice price , quantity is duration in seconds",
    )


def ivr_pricing_create(
    model_id: str,
    model_name: str,
    unit_quantity: int,
    unit_cost: float,
    provider: ModelProvider,
    pricing_url: str = "",
    notes: str = "",
):
    obj, created = ModelPricing.objects.get_or_create(
        model_id=model_id,
        sku=ModelSku.ivr_call,
        defaults=dict(
            model_name=model_name,
            unit_cost=unit_cost,
            unit_quantity=unit_quantity,
            category=category,
            provider=provider,
            pricing_url=pricing_url,
            notes=notes,
        ),
    )
    if created:
        print(f"created {obj}")
