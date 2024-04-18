from django.db import models

from bots.custom_fields import CustomURLField
from daras_ai_v2.stable_diffusion import InpaintingModels

max_digits = 15
decimal_places = 10


class UsageCost(models.Model):
    saved_run = models.ForeignKey(
        "bots.SavedRun", on_delete=models.CASCADE, related_name="usage_costs"
    )
    pricing = models.ForeignKey(
        "usage_costs.ModelPricing", on_delete=models.CASCADE, related_name="usage_costs"
    )

    quantity = models.PositiveIntegerField()
    unit_cost = models.DecimalField(
        max_digits=max_digits,
        decimal_places=decimal_places,
        help_text="The cost per unit, recorded at the time of the usage.",
    )
    unit_quantity = models.PositiveIntegerField(
        help_text="The quantity of the unit (e.g. 1000 tokens), recorded at the time of the usage."
    )

    dollar_amount = models.DecimalField(
        max_digits=max_digits,
        decimal_places=decimal_places,
        help_text="The dollar amount, calculated as unit_cost x quantity / unit_quantity.",
    )

    notes = models.TextField(default="", blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"{self.saved_run} - {self.pricing} - {self.quantity}"


class ModelCategory(models.IntegerChoices):
    LLM = 1, "LLM"
    SELF_HOSTED = 2, "Self-Hosted"


class ModelProvider(models.IntegerChoices):
    openai = 1, "OpenAI"
    google = 2, "Google"
    together_ai = 3, "TogetherAI"
    azure_openai = 4, "Azure OpenAI"
    anthropic = 6, "Anthropic"

    aks = 5, "Azure Kubernetes Service"


def get_model_choices():
    from daras_ai_v2.language_model import LargeLanguageModels
    from recipes.DeforumSD import AnimationModels
    from daras_ai_v2.stable_diffusion import Text2ImgModels, Img2ImgModels

    return (
        [(api.name, api.value) for api in LargeLanguageModels]
        + [(model.name, model.label) for model in AnimationModels]
        + [(model.name, model.value) for model in Text2ImgModels]
        + [(model.name, model.value) for model in Img2ImgModels]
        + [(model.name, model.value) for model in InpaintingModels]
        + [("wav2lip", "LipSync (wav2lip)")]
    )


class ModelSku(models.IntegerChoices):
    llm_prompt = 1, "LLM Prompt"
    llm_completion = 2, "LLM Completion"

    gpu_ms = 3, "GPU Milliseconds"


class ModelPricing(models.Model):
    model_id = models.TextField(
        help_text="The model ID. Model ID + SKU should be unique together."
    )
    sku = models.IntegerField(
        choices=ModelSku.choices,
        help_text="The model's SKU. Model ID + SKU should be unique together.",
    )

    unit_cost = models.DecimalField(
        max_digits=max_digits,
        decimal_places=decimal_places,
        help_text="The cost per unit.",
    )
    unit_quantity = models.PositiveIntegerField(
        help_text="The quantity of the unit. (e.g. 1000 tokens)", default=1
    )

    category = models.IntegerField(
        choices=ModelCategory.choices,
        help_text="The category of the model. Only used for Display purposes.",
    )
    provider = models.IntegerField(
        choices=ModelProvider.choices,
        help_text="The provider of the model. Only used for Display purposes.",
    )
    model_name = models.CharField(
        max_length=255,
        choices=get_model_choices(),
        help_text="The name of the model. Only used for Display purposes.",
    )

    notes = models.TextField(
        default="",
        blank=True,
        help_text="Any notes about the pricing. (e.g. how the pricing was calculated)",
    )
    pricing_url = CustomURLField(
        default="", blank=True, help_text="The URL of the pricing."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["model_id", "sku"]
        indexes = [
            models.Index(fields=["model_id", "sku"]),
        ]

    def __str__(self):
        return f"{self.get_provider_display()} / {self.get_model_name_display()} / {self.get_sku_display()}"
