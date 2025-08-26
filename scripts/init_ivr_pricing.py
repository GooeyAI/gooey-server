from usage_costs.twilio_usage_cost import IVRPlatformMedium
from usage_costs.models import ModelProvider, ModelSku, ModelPricing, ModelCategory

category = ModelCategory.IVR


def run():
    ivr_pricing_create(
        model_id=IVRPlatformMedium.twilio_voice.value,
        sku=ModelSku.ivr_call,
        model_name=IVRPlatformMedium.twilio_voice.name,
        unit_cost=0.0085,
        unit_quantity=60,
        provider=ModelProvider.twilio,
        pricing_url="https://www.twilio.com/en-us/voice/pricing/us",
        notes="cost is per minute, quantity is duration in seconds. actual unit cost ends up varying based on the number.",
    )


def ivr_pricing_create(
    model_id: str,
    sku: ModelSku,
    model_name: str,
    unit_quantity: int,
    unit_cost: float,
    provider: ModelProvider,
    pricing_url: str = "",
    notes: str = "",
):
    obj, created = ModelPricing.objects.get_or_create(
        model_id=model_id,
        sku=sku,
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
