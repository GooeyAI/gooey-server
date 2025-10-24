from django.db import models


class Category(models.IntegerChoices):
    Video = (1, "Video")
    Audio = (2, "Audio")


class VideoModelSpec(models.Model):
    name = models.TextField(
        unique=True,
        help_text="The name of the model to be used in user-facing API calls. WARNING: Don't edit this field after it's been used in a workflow.",
    )
    label = models.TextField(
        help_text="The label of the model to be used in the UI.",
    )
    model_id = models.TextField(
        help_text="The internal API provider / huggingface model id.",
    )
    schema = models.JSONField(
        help_text="The schema of the model parameters.",
        default=dict,
    )

    category = models.IntegerField(
        choices=Category.choices,
        help_text="Model category: generates Audio, Video, etc.",
        null=True,
    )

    pricing = models.ForeignKey(
        "usage_costs.ModelPricing",
        on_delete=models.SET_NULL,
        related_name="video_model_specs",
        null=True,
        blank=True,
        default=None,
        help_text="The pricing of the model. Only for display purposes. "
        "The actual pricing lookup uses the model_id, so make sure the video model's model_id matches the pricing's model_id."
        "To setup a price multiplier, create a WorkflowMetadata for the workflow and set the price_multiplier field.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.label} ({self.model_id})"
