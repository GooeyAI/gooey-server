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
        "created_at",
        "updated_at",
    ]

    list_filter = [
        "pricing__category",
        "pricing__provider",
        "category",
        "created_at",
        "updated_at",
    ]

    search_fields = ["name", "label", "model_id", "category"] + [
        f"pricing__{field}" for field in ModelPricingAdmin.search_fields
    ]
    autocomplete_fields = ["pricing"]

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
                    "schema",
                    "pricing",
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
