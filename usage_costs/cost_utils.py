from loguru import logger

from celeryapp.tasks import get_running_saved_run
from usage_costs.models import (
    UsageCost,
    ModelSku,
    ModelPricing,
)


def record_cost_auto(model: str, sku: ModelSku, quantity: int, **kwargs):
    """
    Record a usage cost for the given model and SKU.

    Args:
        model (str): The model ID.
        sku (ModelSku): The SKU for the usage.
        quantity (int): The quantity of usage.
        **kwargs: Optional keyword arguments for special SKUs.
            For ModelSku.ivr_call, must include:
                - ivr_price_per_minute (float): Price per minute (required for IVR calls).
    """
    sr = get_running_saved_run()
    if not sr:
        return

    try:
        pricing = ModelPricing.objects.get(model_id=model, sku=sku)
    except ModelPricing.DoesNotExist as e:
        logger.warning(f"Cant find pricing for {model=} {sku=}: {e=}")
        return

    match sku:
        case ModelSku.ivr_call:
            price_per_minute = kwargs.get("ivr_price_per_minute")
            if price_per_minute is None:
                raise ValueError(
                    "ivr_price_per_minute is required for IVR call cost calculations"
                )
            dollar_amount = quantity * price_per_minute / 60
            unit_cost_for_record = price_per_minute

        case _:
            dollar_amount = pricing.unit_cost * quantity / pricing.unit_quantity
            unit_cost_for_record = pricing.unit_cost

    UsageCost.objects.create(
        saved_run=sr,
        pricing=pricing,
        quantity=quantity,
        unit_cost=unit_cost_for_record,
        unit_quantity=pricing.unit_quantity,
        dollar_amount=dollar_amount,
    )
