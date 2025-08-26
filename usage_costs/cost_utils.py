from __future__ import annotations

import typing

from loguru import logger


if typing.TYPE_CHECKING:
    from usage_costs.models import ModelSku, ModelPricing, UsageCost
    from bots.models.saved_run import SavedRun


def record_cost_auto(model: str, sku: ModelSku, quantity: int) -> UsageCost | None:
    from celeryapp.tasks import get_running_saved_run

    sr = get_running_saved_run()
    if not sr:
        return None
    pricing = get_model_pricing(model, sku)
    if not pricing:
        return None
    return create_usage_cost(
        sr=sr,
        pricing=pricing,
        quantity=quantity,
        unit_cost=pricing.unit_cost,
        unit_quantity=pricing.unit_quantity,
    )


def get_model_pricing(model_id: str, sku: ModelSku) -> ModelPricing | None:
    from usage_costs.models import ModelPricing

    try:
        return ModelPricing.objects.get(model_id=model_id, sku=sku)
    except ModelPricing.DoesNotExist:
        logger.warning(f"Model pricing not found for model_id: {model_id}, sku: {sku}")
        return None


def create_usage_cost(
    sr: SavedRun,
    pricing: ModelPricing,
    quantity: int,
    unit_cost: float,
    unit_quantity: int,
) -> UsageCost:
    from usage_costs.models import UsageCost

    return UsageCost.objects.create(
        saved_run=sr,
        pricing=pricing,
        quantity=quantity,
        unit_cost=unit_cost,
        unit_quantity=unit_quantity,
        dollar_amount=unit_cost * quantity / unit_quantity,
    )
