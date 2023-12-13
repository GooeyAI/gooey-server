from django.contrib import admin
from cost import models

# Register your models here.


@admin.register(models.Cost)
class CostAdmin(admin.ModelAdmin):
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
