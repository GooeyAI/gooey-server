from decimal import Decimal

from daras_ai_v2.gpu_server import build_queue_name
from daras_ai_v2.stable_diffusion import (
    Text2ImgModels,
    Img2ImgModels,
    InpaintingModels,
    text2img_model_ids,
    img2img_model_ids,
    inpaint_model_ids,
)
from recipes.DeforumSD import AnimationModels
from usage_costs.models import ModelPricing
from usage_costs.models import ModelSku, ModelCategory, ModelProvider

category = ModelCategory.SELF_HOSTED


def run():
    for model in AnimationModels:
        add_model(model.value, model.name)
    for model_enum, model_ids in [
        (Text2ImgModels, text2img_model_ids),
        (Img2ImgModels, img2img_model_ids),
        (InpaintingModels, inpaint_model_ids),
    ]:
        for m in model_enum:
            if "dall_e" in m.name:
                continue
            try:
                add_model(model_ids[m], m.name)
            except KeyError:
                pass


def add_model(model_id, model_name):
    ModelPricing.objects.get_or_create(
        model_id=build_queue_name("gooey-gpu", model_id),
        sku=ModelSku.gpu_ms,
        defaults=dict(
            model_name=model_name,
            unit_cost=Decimal("3.673"),
            unit_quantity=3600000,
            category=category,
            provider=ModelProvider.aks,
            notes="NC24ads A100 v4 - 1 X A100 - Pay as you go - $3.6730/hour",
            pricing_url="https://azure.microsoft.com/en-in/pricing/details/virtual-machines/linux/#pricing",
        ),
    )
