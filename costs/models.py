from django.db import models
from daras_ai_v2.language_model import LLMApis


# class Provider(models.TextChoices):
#     vertex_ai = "vertex_ai", "Vertex AI"
#     openai = "openai", "OpenAI"
#     together = "together", "Together"


class Product(models.TextChoices):
    gpt_4_vision = (
        "gpt-4-vision-preview",
        "gpt-4-vision-preview",
    )


class UsageCost(models.Model):
    saved_run = models.ForeignKey(
        "bots.SavedRun",
        on_delete=models.CASCADE,
        related_name="usage_costs",
        null=True,
        default=None,
        blank=True,
        help_text="The run that was last saved by the user.",
    )

    provider_pricing = models.ForeignKey(
        "costs.ProviderPricing",
        on_delete=models.CASCADE,
        related_name="usage_costs",
        null=True,
        default=None,
    )
    quantity = models.IntegerField(default=1)
    notes = models.TextField(default="", blank=True)
    dollar_amt = models.DecimalField(
        max_digits=13,
        decimal_places=8,
    )
    created_at = models.DateTimeField(auto_now_add=True)


class ProviderPricing(models.Model):
    class Type(models.TextChoices):
        LLM = "LLM", "LLM"

    class Param(models.TextChoices):
        input = "Input", "input"
        output = "Output", "output"

    type = models.TextField(choices=Type.choices)
    provider = models.TextField(choices=LLMApis.choices())
    product = models.TextField(choices=Product.choices)
    param = models.TextField(choices=Param.choices)
    cost = models.DecimalField(max_digits=13, decimal_places=8)
    unit = models.TextField(default="")
    notes = models.TextField(default="")
    created_at = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    updated_by = models.TextField(default="")
    pricing_url = models.TextField(default="")

    def __str__(self):
        return self.type + " " + self.provider + " " + self.product + " " + self.param
