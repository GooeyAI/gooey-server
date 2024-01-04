from django.db import models
from daras_ai_v2.language_model import LargeLanguageModels


class Provider(models.IntegerChoices):
    OpenAI = 1, "OpenAI"
    GPT_4 = 2, "GPT-4"
    dalle_e = 3, "dalle-e"
    whisper = 4, "whisper"
    GPT_3_5 = 5, "GPT-3.5"


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

    provider = models.IntegerField(choices=Provider.choices)
    model = models.TextField("model", blank=True)
    param = models.TextField(
        "param", blank=True
    )  # contains input/output tokens and quantity
    notes = models.TextField(default="", blank=True)
    calculation_notes = models.TextField(default="", blank=True)
    dollar_amt = models.DecimalField(
        max_digits=13,
        decimal_places=8,
    )
    created_at = models.DateTimeField(auto_now_add=True)


class ProviderPricing(models.Model):
    class Type(models.TextChoices):
        LLM = "LLM"

    class Param(models.TextChoices):
        input = "input"
        output = "output"
        input_image = "input image"
        output_image = "output image"

    type = models.TextField(choices=Type.choices)
    provider = models.IntegerField(choices=Provider.choices)
    product = models.TextField(choices=LargeLanguageModels.choices())
    param = models.TextField(choices=Param.choices)
    cost = models.DecimalField(max_digits=13, decimal_places=8)
    unit = models.TextField(default="")
    notes = models.TextField(default="")
    created_at = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    updated_by = models.TextField(default="")
    pricing_url = models.TextField(default="")
