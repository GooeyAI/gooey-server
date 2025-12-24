from django.db import models


class ModelProvider(models.IntegerChoices):
    openai = 1, "OpenAI"
    openai_audio = 16, "Openai Audio"
    azure_openai = 4, "Azure OpenAI"
    google = 2, "Google"
    together_ai = 3, "TogetherAI"
    anthropic = 6, "Anthropic"
    groq = 7, "groq"
    fireworks = 8, "Fireworks AI"
    mistral = 9, "Mistral AI"
    sarvam = 10, "sarvam.ai"
    fal_ai = 11, "fal.ai"
    twilio = 12, "Twilio"
    sea_lion = 13, "sea-lion.ai"
    publicai = 14, "PublicAI"
    modal = 15, "Modal"
    aks = 5, "Azure Kubernetes Service"


class AIModelSpecQuerySet(models.QuerySet):
    def get_queryset(self):
        return super().get_queryset().filter(is_deprecated=False)


class AIModelSpec(models.Model):
    class Categories(models.IntegerChoices):
        video = (1, "🎥 Video")
        audio = (2, "🎵 Audio")
        llm = (3, "💬 LLM")

    category = models.IntegerField(
        choices=Categories.choices,
        help_text="Model category: generates Audio, Video, etc.",
        null=True,
        default=Categories.video,
    )

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

    provider = models.IntegerField(
        choices=ModelProvider.choices,
        help_text="The API provider for this model.",
        default=ModelProvider.modal,
    )
    is_deprecated = models.BooleanField(default=False)
    redirect_to = models.ForeignKey(
        "ai_models.AIModelSpec",
        on_delete=models.SET_NULL,
        related_name="redirect_to_ai_model_specs",
        null=True,
        blank=True,
        default=None,
    )
    version = models.FloatField(default=1)

    llm_context_window = models.IntegerField(default=0, verbose_name="Context Window")
    llm_max_output_tokens = models.IntegerField(
        default=0, verbose_name="Max Output Tokens"
    )
    llm_is_chat_model = models.BooleanField(default=True, verbose_name="Chat Model")
    llm_is_vision_model = models.BooleanField(
        default=False, verbose_name="Vision Model"
    )
    llm_is_thinking_model = models.BooleanField(
        default=False, verbose_name="Thinking Model"
    )
    llm_supports_json = models.BooleanField(default=False, verbose_name="Supports JSON")
    llm_supports_temperature = models.BooleanField(
        default=True, verbose_name="Supports Temperature"
    )
    llm_supports_input_audio = models.BooleanField(
        default=False, verbose_name="Supports Input Audio"
    )
    llm_is_audio_model = models.BooleanField(default=False, verbose_name="Audio Model")

    pricing = models.ForeignKey(
        "usage_costs.ModelPricing",
        on_delete=models.SET_NULL,
        related_name="ai_model_specs",
        null=True,
        blank=True,
        default=None,
        help_text="The pricing of the model. Only for display purposes. "
        "The actual pricing lookup uses the model_id, so make sure the video model's model_id matches the pricing's model_id."
        "To setup a price multiplier, create a WorkflowMetadata for the workflow and set the price_multiplier field.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = AIModelSpecQuerySet.as_manager()

    class Meta:
        verbose_name = "AI Model Spec"

    def __str__(self):
        return f"{self.label} ({self.model_id})"
