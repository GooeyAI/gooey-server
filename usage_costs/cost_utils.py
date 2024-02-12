from loguru import logger

from daras_ai_v2.query_params import gooey_get_query_params
from daras_ai_v2.query_params_util import extract_query_params
from usage_costs.models import (
    UsageCost,
    ModelSku,
    ModelPricing,
)


def record_cost_auto(model: str, sku: ModelSku, quantity: int):
    from bots.models import SavedRun

    _, run_id, uid = extract_query_params(gooey_get_query_params())
    if not run_id or not uid:
        return

    try:
        pricing = ModelPricing.objects.get(model_id=model, sku=sku)
    except ModelPricing.DoesNotExist as e:
        logger.warning(f"Cant find pricing for {model=} {sku=}: {e=}")
        return

    saved_run = SavedRun.objects.get(run_id=run_id, uid=uid)

    UsageCost.objects.create(
        saved_run=saved_run,
        pricing=pricing,
        quantity=quantity,
        unit_cost=pricing.unit_cost,
        unit_quantity=pricing.unit_quantity,
        dollar_amount=pricing.unit_cost * quantity / pricing.unit_quantity,
    )
