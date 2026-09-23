"""Eco cost of a run, derived from its usage cost rows.

Nothing is stored. A UsageCost row already records the model and the token
count, which is everything `ecocost` needs, so the estimate is computed on
read. That keeps the schema free of ecocost while its methodology is still
moving, and lets `ecocost` live in its own repo as a plain dependency.
"""

from __future__ import annotations

import typing
from collections import defaultdict

from loguru import logger

if typing.TYPE_CHECKING:
    from bots.models import SavedRun

# a run is as sure as its least sure model
CONFIDENCE_LEVELS = ("high", "medium", "low")

# Who serves a Gooey model call, for ``ecocost.estimate``. ecocost resolves a
# base_url from the hosts providers publish and a closed model's vendor itself;
# these are the open-model routes only Gooey knows (``get_openai_client`` in
# daras_ai_v2/language_model.py). Anything else gets ecocost's US defaults.
MODEL_PREFIX_TO_PROVIDER: tuple[tuple[str, str], ...] = (
    ("accounts/fireworks/", "fireworks"),
    ("mistral-", "mistral"),
    ("mistral/", "mistral"),  # litellm
    ("aisingapore/", "sea-lion"),
    ("AI71ai/", "modal"),
)


def run_eco_cost(sr: SavedRun) -> dict | None:
    """Summed estimate for a run, or None if it has no LLM token usage or a
    model in it is not in ecocost."""
    import ecocost
    from ai_models.models import AIModelSpec, ModelProvider
    from usage_costs.models import ModelSku

    token_kwarg = {
        ModelSku.llm_prompt: "input_tokens",
        ModelSku.llm_completion: "output_tokens",
    }
    tokens_by_model: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for model_id, sku, quantity in sr.usage_costs.filter(
        pricing__sku__in=token_kwarg
    ).values_list("pricing__model_id", "pricing__sku", "quantity"):
        tokens_by_model[model_id][token_kwarg[sku]] += int(quantity)
    if not tokens_by_model:
        return None

    specs = {
        spec["model_id"]: spec
        for spec in AIModelSpec.objects.filter(model_id__in=tokens_by_model)
        .order_by("-is_deprecated", "updated_at")  # live, newest spec wins
        .values("model_id", "provider", "base_url")
    }
    # A run is labelled only if every model in it can be estimated: a partial
    # sum would understate it with nothing to say so. Any other failure is
    # caught by the caller, which drops the label.
    estimates = []
    for model_id, tokens in tokens_by_model.items():
        spec = specs.get(model_id) or {}
        route = ecocost_route(
            provider_enum=spec and ModelProvider(spec["provider"]).name,
            model_id=model_id,
            base_url=spec.get("base_url") or None,
        )
        try:
            estimates.append(ecocost.estimate(model_id, **route, **tokens))
        except ecocost.UnknownModelError as e:
            logger.info(str(e))
            return None

    return dict(
        co2e_grams=sum(e["carbon"]["value"] for e in estimates),
        co2e_min=sum(e["carbon"]["min"] for e in estimates),
        co2e_max=sum(e["carbon"]["max"] for e in estimates),
        energy_wh=sum(e["energy"]["value"] for e in estimates),
        water_ml=sum(e["water"]["value"] for e in estimates),
        water_onsite_ml=sum(e["water"]["on_site"]["value"] for e in estimates),
        confidence=max(
            (e["confidence"]["level"] for e in estimates),
            key=CONFIDENCE_LEVELS.index,
        ),
        reasons=sorted({r for e in estimates for r in e["confidence"]["reasons"]}),
        # the model that emitted the most carbon decides the region block
        dominant=max(estimates, key=lambda e: e["carbon"]["value"]),
    )


def ecocost_route(
    *, provider_enum: str | None, model_id: str, base_url: str | None = None
) -> dict[str, str]:
    """Keyword arguments for ``ecocost.estimate`` naming who serves the call."""
    if base_url:
        return {"base_url": base_url}
    if provider_enum == "aks":  # Gooey's own Azure cluster; ecocost has no record
        return {"provider": "unknown-us"}
    for prefix, provider in MODEL_PREFIX_TO_PROVIDER:
        if model_id.startswith(prefix):
            return {"provider": provider}
    return {}
