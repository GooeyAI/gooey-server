from __future__ import annotations

import json
import mimetypes
import os
import time
import typing
from decimal import Decimal
from urllib.parse import urlparse

import requests
from furl import furl
from loguru import logger

from daras_ai.image_input import get_mimetype_from_response, upload_file_from_bytes
from daras_ai_v2 import settings
from daras_ai_v2.exceptions import raise_for_status

if typing.TYPE_CHECKING:
    from usage_costs.models import ModelPricing, ModelSku


def generate_on_fal(model_id: str, payload: dict) -> typing.Generator[str, None, dict]:
    r = requests.post(
        str(furl("https://queue.fal.run") / model_id),
        headers=_fal_auth_headers(),
        json=payload,
    )
    raise_for_status(r)
    result = r.json()

    yield from stream_fal_status_events(result["status_url"])

    r = requests.get(result["response_url"], headers=_fal_auth_headers())
    raise_for_status(r)
    _record_fal_cost(model_id, r.headers)
    return _rewrite_fal_asset_urls(r.json())


def _record_fal_cost(model_id: str, response_headers: typing.Mapping[str, str]) -> None:
    """Record UsageCost from the X-Fal-Billable-Units response header.

    The ModelPricing row is expected to exist already; it's seeded by
    `AIModelSpec.save()` for video/audio models and by
    `scripts/init_image_generation_pricing.py` for image generation models.
    """
    from decimal import InvalidOperation

    from usage_costs.cost_utils import record_cost_auto
    from usage_costs.models import ModelSku

    raw_units = response_headers.get("x-fal-billable-units")
    if not raw_units:
        return
    try:
        units = Decimal(raw_units)
    except InvalidOperation:
        return
    if units <= 0:
        return

    record_cost_auto(model=model_id, sku=ModelSku.fal_billable_units, quantity=units)


def format_pricing_notes(models: dict[str, str], sku: ModelSku) -> str | None:
    from usage_costs.models import ModelPricing

    notes_by_id = dict(
        ModelPricing.objects.filter(model_id__in=models.keys(), sku=sku)
        .exclude(notes="")
        .values_list("model_id", "notes")
    )
    lines = []
    for model_id, label in models.items():
        notes = notes_by_id.get(model_id)
        if not notes:
            continue
        lines.append(f"**{label}**: {notes}")
    if not lines:
        return None
    return "\n".join(lines)


def sync_fal_model_pricing(
    model_id: str, *, model_name: str | None = None
) -> "ModelPricing | None":
    """Fetch the current unit price from fal's pricing API and upsert a
    ModelPricing row for (model_id, sku=fal_billable_units).

    Resolves the display category and model_name from the matching AIModelSpec
    row when one exists. For fal image-gen models that live in hardcoded enums
    in `stable_diffusion.py` rather than as AIModelSpec rows, the caller should
    pass `model_name` explicitly (typically the matching enum's `.name`).

    Returns the upserted ModelPricing instance, or None if fal returned no
    pricing data (e.g. unknown endpoint_id, or pure GPU-time billing).
    """
    from ai_models.models import ModelProvider
    from usage_costs.models import ModelPricing, ModelSku

    price_info = _fetch_fal_pricing(model_id)
    if not price_info:
        return None

    unit_price = Decimal(str(price_info["unit_price"]))
    unit = price_info.get("unit") or ""
    category, resolved_name = _resolve_fal_pricing_metadata(model_id)
    notes = f"${_format_unit_price(unit_price)} / {_singularize_unit(unit) or 'unit'}"
    model_name = model_name or resolved_name

    pricing, _ = ModelPricing.objects.update_or_create(
        model_id=model_id,
        sku=ModelSku.fal_billable_units,
        defaults=dict(
            model_name=model_name,
            unit_cost=unit_price,
            unit_quantity=1,
            category=category,
            provider=ModelProvider.fal_ai,
            pricing_url=f"https://fal.ai/models/{model_id}",
            notes=notes,
        ),
    )
    return pricing


def _format_unit_price(price: Decimal) -> str:
    """Render a Decimal price with at least 2 decimal places, no trailing zeros
    beyond that (0.0800 -> 0.08, 0.4 -> 0.40, 0.001 -> 0.001, 1 -> 1.00)."""
    s = format(price.normalize(), "f")
    whole, _, frac = s.partition(".")
    if len(frac) < 2:
        frac = frac.ljust(2, "0")
    return f"{whole}.{frac}"


def _singularize_unit(unit: str) -> str:
    unit = (unit or "").strip().lower()
    if unit.endswith("s"):
        return unit[:-1]
    return unit


def _resolve_fal_pricing_metadata(model_id: str) -> tuple[int, str]:
    """Return (category, model_name) for a fal model_id, sourced from
    AIModelSpec when available. Defaults to IMAGE_GENERATION otherwise
    (fal image models live in hardcoded enums in stable_diffusion.py rather
    than as AIModelSpec rows; category is display-only so this is harmless).
    """
    from ai_models.models import AIModelSpec
    from usage_costs.models import ModelCategory

    spec = (
        AIModelSpec.objects.filter(model_id=model_id).only("name", "category").first()
    )
    if spec is None:
        return ModelCategory.IMAGE_GENERATION, model_id
    category = _category_from_aimodelspec(spec)
    return category, spec.name


def _category_from_aimodelspec(spec) -> "int | None":
    """Map AIModelSpec.category to a ModelCategory for ModelPricing display."""
    from ai_models.models import AIModelSpec
    from usage_costs.models import ModelCategory

    match spec.category:
        case AIModelSpec.Categories.video:
            return ModelCategory.VIDEO_GENERATION
        case AIModelSpec.Categories.audio:
            return ModelCategory.AUDIO_GENERATION
        case AIModelSpec.Categories.llm:
            return ModelCategory.LLM


FAL_PRICING_API_URL = "https://api.fal.ai/v1/models/pricing"


def _fetch_fal_pricing(model_id: str) -> dict | None:
    r = requests.get(
        FAL_PRICING_API_URL,
        params={"endpoint_id": model_id},
        headers=_fal_auth_headers(),
        timeout=10,
    )
    raise_for_status(r)
    prices = r.json().get("prices") or []
    for entry in prices:
        if entry.get("endpoint_id") == model_id:
            return entry
    return None


def stream_fal_status_events(
    status_url: str,
    *,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> typing.Iterator[str]:
    stream_url = furl(status_url).add(path="stream", query_params=dict(logs="1")).url

    for attempt in range(max_retries):
        try:
            response = requests.get(
                stream_url, headers=_fal_auth_headers(), stream=True
            )
            raise_for_status(response)
            for event_data in stream_sse_json(response):
                if event_data["status"] == "COMPLETED":
                    return
                logs = event_data["logs"]
                if not logs:
                    continue
                yield "`" + logs[-1]["message"] + "`"
        except requests.exceptions.ChunkedEncodingError:
            if attempt >= max_retries - 1:
                raise
            logger.warning(
                f"ChunkedEncodingError: [{attempt + 1}/{max_retries}] retrying in {retry_delay} seconds"
            )
            time.sleep(retry_delay)
        else:
            return


def stream_sse_json(response: requests.Response) -> typing.Iterator[dict]:
    with response:
        for line in response.iter_lines():
            if not line:
                continue
            decoded_line = line.decode("utf-8")
            if not decoded_line.startswith("data: "):
                continue
            event_data = decoded_line.removeprefix("data: ")
            yield json.loads(event_data)


def _fal_auth_headers():
    return {
        "Authorization": f"Key {settings.FAL_API_KEY}",
        "X-Fal-Object-Lifecycle-Preference": json.dumps(
            {"expiration_duration_seconds": 3600}
        ),
    }


def _rewrite_fal_asset_urls(value: typing.Any) -> typing.Any:
    match value:
        case str() if _is_fal_asset_url(value):
            filename = os.path.basename(urlparse(value).path) or "fal_asset"
            return _reupload_fal_asset_url(value, filename=filename)
        case dict():
            out = {}
            for key, child in value.items():
                out[key] = _rewrite_fal_asset_urls(child)
            return out
        case list():
            return [_rewrite_fal_asset_urls(item) for item in value]
        case _:
            return value


def _is_fal_asset_url(url: str) -> bool:
    try:
        f = furl(url)
    except Exception:
        return False
    return "fal.media" in f.origin


def _reupload_fal_asset_url(url: str, *, filename: str) -> str:
    r = requests.get(url)
    raise_for_status(r)

    content_type = get_mimetype_from_response(r) or None

    # If FAL returns extensionless filenames, preserve a useful extension.
    if (
        not os.path.splitext(filename)[1]
        and content_type
        and (ext := mimetypes.guess_extension(content_type))
    ):
        filename += ext

    try:
        uploaded_url = upload_file_from_bytes(
            filename, r.content, content_type=content_type
        )
    except Exception:
        logger.exception("Failed to re-upload FAL asset URL {}", url)
        return url

    return uploaded_url
