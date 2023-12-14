from django.contrib import admin
from costs import models

# Register your models here.


@admin.register(models.UsageCost)
class CostsAdmin(admin.ModelAdmin):
    list_display = [
        "run_id",
        "provider",
        "model",
        "param",
        "notes",
        "quantity",
        "calculation_notes",
        "cost",
    ]
