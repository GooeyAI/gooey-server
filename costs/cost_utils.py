from costs.models import UsageCost, ProviderPricing
from bots.models import SavedRun


def get_provider_pricing(
    type: str,
    provider: str,
    product: str,
    param: str,
) -> ProviderPricing:
    print("get_provider_pricing", type, provider, product, param)
    return ProviderPricing.objects.get(
        type=type,
        provider=provider,
        product=product,
        param=param,
    )


def record_cost(
    run_id: str | None,
    uid: str | None,
    provider_pricing: ProviderPricing,
    quantity: int,
) -> UsageCost:
    saved_run = SavedRun.objects.get(run_id=run_id, uid=uid)
    cost = UsageCost(
        saved_run=saved_run,
        provider_pricing=provider_pricing,
        quantity=quantity,
        notes="",
        dollar_amt=provider_pricing.cost * quantity,
        created_at=saved_run.created_at,
    )
    cost.save()
    return cost
