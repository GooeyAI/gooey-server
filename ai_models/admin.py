from django.contrib import admin
from django.db import models

from ai_models.models import AIModelSpec
from gooeysite.custom_widgets import JSONEditorWidget
from usage_costs.admin import ModelPricingAdmin


@admin.register(AIModelSpec)
class AIModelSpecAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "label",
        "model_id",
        "category",
        "is_deprecated",
        "redirect_to",
        "created_at",
        "updated_at",
    ]

    list_filter = [
        "pricing__category",
        "pricing__provider",
        "category",
        "is_deprecated",
        "created_at",
        "updated_at",
    ]

    search_fields = ["name", "label", "model_id", "category"] + [
        f"pricing__{field}" for field in ModelPricingAdmin.search_fields
    ]
    autocomplete_fields = ["pricing", "redirect_to"]

    readonly_fields = ["created_at", "updated_at"]

    fieldsets = [
        (
            "Model Information",
            {
                "fields": [
                    "category",
                    "name",
                    "label",
                    "model_id",
                    "schema",
                    "pricing",
                ]
            },
        ),
        (
            "Provider Settings",
            {
                "fields": [
                    "provider",
                    "is_deprecated",
                    "redirect_to",
                    "version",
                ]
            },
        ),
        (
            "LLM Settings",
            {
                "fields": [
                    "llm_context_window",
                    "llm_max_output_tokens",
                    "llm_is_chat_model",
                    "llm_is_vision_model",
                    "llm_is_thinking_model",
                    "llm_supports_json",
                    "llm_supports_temperature",
                    "llm_supports_input_audio",
                    "llm_is_audio_model",
                ]
            },
        ),
        (
            "Timestamps",
            {
                "fields": [
                    "created_at",
                    "updated_at",
                ]
            },
        ),
    ]

    formfield_overrides = {
        models.JSONField: {"widget": JSONEditorWidget},
    }
