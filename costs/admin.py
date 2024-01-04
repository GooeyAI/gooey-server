from django.contrib import admin
from costs import models

# Register your models here.


@admin.register(models.UsageCost)
class CostsAdmin(admin.ModelAdmin):
    list_display = [
        "saved_run",
        "provider",
        "model",
        "param",
        "notes",
        "calculation_notes",
        "dollar_amt",
        "created_at",
    ]


@admin.register(models.ProviderPricing)
class ProviderAdmin(admin.ModelAdmin):
    list_display = [
        "type",
        "provider",
        "product",
        "param",
        "cost",
        "unit",
        "created_at",
        "last_updated",
        "updated_by",
        "pricing_url",
    ]
