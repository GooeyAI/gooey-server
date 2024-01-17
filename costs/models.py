from django.db import models


class Provider(models.TextChoices):
    vertex_ai = "Vertex AI"
    openai = "OpenAI"
    together = "Together"
    Azure = "Azure"


class Product(models.TextChoices):
    gpt_4_vision = (
        "gpt-4-vision-preview",
        "gpt-4-vision-preview",
    )
    gpt_4_turbo = (
        "('openai-gpt-4-turbo-prod-ca-1', 'gpt-4-1106-preview')",
        "('openai-gpt-4-turbo-prod-ca-1', 'gpt-4-1106-preview')",
    )

    gpt_4_32k = (
        "('openai-gpt-4-prod-ca-1', 'gpt-4')",
        "('openai-gpt-4-prod-ca-1', 'gpt-4')",
    )
    gpt_3_5_turbo = (
        "gpt-3.5-turbo",
        "gpt-3.5-turbo",
    )
    gpt_3_5_turbo_16k = (
        "gpt-3.5-turbo-16k",
        "gpt-3.5-turbo-16k",
    )
    text_davinci_003 = (
        "text-davinci-003",
        "text-davinci-003",
    )
    text_davinci_002 = (
        "text-davinci-002",
        "text-davinci-002",
    )
    code_davinci_002 = (
        "code-davinci-002",
        "code-davinci-002",
    )
    text_curie_001 = (
        "text-curie-001",
        "text-curie-001",
    )
    text_babbage_001 = (
        "text-babbage-001",
        "text-babbage-001",
    )
    text_ada_001 = (
        "text-ada-001",
        "text-ada-001",
    )
    palm2_text = (
        "text-bison",
        "text-bison",
    )
    palm2_chat = (
        "chat-bison",
        "chat-bison",
    )
    llama2_70b_chat = (
        "togethercomputer/llama-2-70b-chat",
        "togethercomputer/llama-2-70b-chat",
    )
    NC24ads_A100_v4_1_year_plan = (
        "NC24ads A100 v4-1 year plan",
        "NC24ads A100 v4-1 year plan",
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
    class Group(models.TextChoices):
        LLM = "LLM", "LLM"
        GPU = "GPU", "GPU"

    class Param(models.TextChoices):
        input = "Input", "input"
        output = "Output", "output"

    type = models.TextField(choices=Group.choices)
    provider = models.TextField(choices=Provider.choices)
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
