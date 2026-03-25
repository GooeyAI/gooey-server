from django.contrib import admin
from django.db import models

from ai_models.models import AIModelSpec
from gooeysite.custom_widgets import JSONEditorWidget
from usage_costs.admin import ModelPricingAdmin
from django import forms


llm_fields = [
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

av_fields = [
    "paid_only",
]


class AIModelSpecForm(forms.ModelForm):
    class Meta:
        model = AIModelSpec
        fields = "__all__"
        widgets = {
            "category": forms.Select(
                attrs={
                    "--hideshow-fields": ",".join(llm_fields + av_fields),
                    f"--show-on-{AIModelSpec.Categories.llm}": ",".join(llm_fields),
                    f"--show-on-{AIModelSpec.Categories.audio}": ",".join(av_fields),
                    f"--show-on-{AIModelSpec.Categories.video}": ",".join(av_fields),
                }
            ),
        }

    class Media:
        js = [
            "https://cdn.jsdelivr.net/gh/scientifichackers/django-hideshow@0.0.1/hideshow.js",
        ]


@admin.register(AIModelSpec)
class AIModelSpecAdmin(admin.ModelAdmin):
    form = AIModelSpecForm

    list_display = [
        "name",
        "label",
        "model_id",
        "category",
        "priority",
        "paid_only",
        "is_deprecated",
        "redirect_to",
        "created_at",
        "updated_at",
    ]

    list_filter = [
        "category",
        "provider",
        "paid_only",
        "is_deprecated",
        "created_at",
        "updated_at",
    ]

    search_fields = ["name", "label", "model_id", "category"] + [
        f"pricing__{field}" for field in ModelPricingAdmin.search_fields
    ]
    autocomplete_fields = ["pricing", "redirect_to"]

    readonly_fields = [
        "created_at",
        "updated_at",
    ]

    fieldsets = [
        (
            "Model Information",
            {
                "fields": [
                    "category",
                    "name",
                    "label",
                    "model_id",
                    "priority",
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
            "Model Settings",
            {
                "fields": [
                    "paid_only",
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
            "API Settings",
            {
                "fields": [
                    "api_key",
                    "base_url",
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
