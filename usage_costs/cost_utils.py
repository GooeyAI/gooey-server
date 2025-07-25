from decimal import Decimal
from loguru import logger

from celeryapp.tasks import get_running_saved_run
from usage_costs.models import (
    UsageCost,
    ModelSku,
    ModelPricing,
)


def record_cost_auto(model: str, sku: ModelSku, quantity: int, notes: str = ""):
    sr = get_running_saved_run()
    if not sr:
        return

    try:
        pricing = ModelPricing.objects.get(model_id=model, sku=sku)
    except ModelPricing.DoesNotExist as e:
        logger.warning(f"Cant find pricing for {model=} {sku=}: {e=}")
        return

    # Handle type conversion for IVR calls specifically
    if sku == ModelSku.ivr_call:
        dollar_amount = (
            pricing.unit_cost * Decimal(str(quantity)) / pricing.unit_quantity
        )
    else:
        dollar_amount = pricing.unit_cost * quantity / pricing.unit_quantity

    UsageCost.objects.create(
        saved_run=sr,
        pricing=pricing,
        quantity=quantity,
        unit_cost=pricing.unit_cost,
        unit_quantity=pricing.unit_quantity,
        dollar_amount=dollar_amount,
        notes=notes,
    )
