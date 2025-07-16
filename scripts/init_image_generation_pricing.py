from daras_ai_v2.stable_diffusion import Text2ImgModels, Img2ImgModels
from usage_costs.models import ModelSku, ModelCategory, ModelProvider, ModelPricing


def run():
    # FLUX.1 Pro Kontext (fal.ai) - Per-image pricing (2.5x fal base price)
    image_generation_pricing_create(
        model_id="fal-ai/flux-pro/kontext",
        model_name=Img2ImgModels.flux_pro_kontext.name,
        unit_cost_text_input=None,  # No separate text input cost
        unit_cost_image_input=None,  # No separate image input cost
        unit_cost_output=0.10,  # $0.10 per image (10 credits at 100 credits per dollar)
        unit_quantity=1,  # 1 image
        provider=ModelProvider.fal_ai,
        pricing_url="https://fal.ai/models/fal-ai/flux-pro/kontext",
        notes="Per-image pricing: $0.10 per generated image (2.5x base fal pricing)",
    )

    # GPT Image 1 (OpenAI) - Token-based pricing
    image_generation_pricing_create(
        model_id="gpt-image-1",
        model_name=Text2ImgModels.gpt_image_1.name,
        unit_cost_text_input=5.0,  # $5 per 1M tokens
        unit_cost_image_input=10.0,  # $10 per 1M tokens
        unit_cost_output=40.0,  # $40 per 1M tokens
        unit_quantity=1e6,  # 1 million tokens
        provider=ModelProvider.openai,
        pricing_url="https://openai.com/api/pricing",
        notes="Token-based pricing: $5/1M text input tokens, $10/1M image input tokens, $40/1M output tokens",
    )


def image_generation_pricing_create(
    model_id: str,
    model_name: str,
    unit_cost_text_input: float | None,
    unit_cost_image_input: float | None,
    unit_cost_output: float,
    unit_quantity: int,
    provider: ModelProvider,
    pricing_url: str = "",
    notes: str = "",
):
    """
    Create pricing entries for image generation models.

    Args:
        model_id: The model identifier
        model_name: Display name of the model
        unit_cost_text_input: Cost per text input token/request (None if not supported)
        unit_cost_image_input: Cost per image input (None if not supported)
        unit_cost_output: Cost per image output generated
        unit_quantity: Quantity unit (typically 1 for image generation)
        provider: Model provider
        pricing_url: URL to pricing information
        notes: Additional notes about pricing
    """
    # Text Input pricing (for text-to-image generation) - only if supported
    if unit_cost_text_input is not None:
        obj, created = ModelPricing.objects.get_or_create(
            model_id=model_id,
            sku=ModelSku.llm_prompt,
            defaults=dict(
                model_name=model_name,
                unit_cost=unit_cost_text_input,
                unit_quantity=unit_quantity,
                category=ModelCategory.IMAGE_GENERATION,
                provider=provider,
                pricing_url=pricing_url,
                notes=notes,
            ),
        )
        if created:
            print(f"Created text input pricing: {obj}")

    # Image Input pricing (for image-to-image generation, editing) - only if supported
    if unit_cost_image_input is not None:
        obj, created = ModelPricing.objects.get_or_create(
            model_id=model_id,
            sku=ModelSku.input_image_tokens,
            defaults=dict(
                model_name=model_name,
                unit_cost=unit_cost_image_input,
                unit_quantity=unit_quantity,
                category=ModelCategory.IMAGE_GENERATION,
                provider=provider,
                pricing_url=pricing_url,
                notes=notes,
            ),
        )
        if created:
            print(f"Created image input pricing: {obj}")

    # Output pricing (for generated images) - always required
    obj, created = ModelPricing.objects.get_or_create(
        model_id=model_id,
        sku=ModelSku.output_image_tokens,
        defaults=dict(
            model_name=model_name,
            unit_cost=unit_cost_output,
            unit_quantity=unit_quantity,
            category=ModelCategory.IMAGE_GENERATION,
            provider=provider,
            pricing_url=pricing_url,
            notes=notes,
        ),
    )
    if created:
        print(f"Created output pricing: {obj}")
