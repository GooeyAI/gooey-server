from django.db import models


# class CostQuerySet(models.QuerySet):


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

    class Provider(models.IntegerChoices):
        OpenAI = 1, "OpenAI"
        GPT_4 = 2, "GPT-4"
        dalle_e = 3, "dalle-e"
        whisper = 4, "whisper"
        GPT_3_5 = 5, "GPT-3.5"

    provider = models.IntegerField(choices=Provider.choices)
    model = models.TextField("model", blank=True)
    param = models.TextField("param", blank=True)  # combine with quantity as JSON obj
    notes = models.TextField(default="", blank=True)
    quantity = models.JSONField(default=dict, blank=True)
    calculation_notes = models.TextField(default="", blank=True)
    dollar_amt = models.DecimalField(
        max_digits=13,
        decimal_places=8,
    )
    created_at = models.DateTimeField(auto_now_add=True)
