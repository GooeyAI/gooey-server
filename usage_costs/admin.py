from django.contrib import admin

from bots.admin_links import open_in_new_tab, change_obj_url
from daras_ai.text_format import format_number_with_suffix
from usage_costs import models


class CostQtyMixin:
    @admin.display(description="Cost / Qty", ordering="unit_cost")
    def cost_qty(self, obj: models.ModelPricing | models.UsageCost):
        return f"${obj.unit_cost.normalize()} / {format_number_with_suffix(obj.unit_quantity)}"


@admin.register(models.UsageCost)
class UsageCostAdmin(admin.ModelAdmin, CostQtyMixin):
    list_display = [
        "__str__",
        "cost_qty",
        "quantity",
        "display_dollar_amount",
        "view_pricing",
        "view_saved_run",
        "view_parent_published_run",
        "notes",
        "created_at",
    ]
    autocomplete_fields = ["saved_run", "pricing"]
    list_filter = [
        "saved_run__workflow",
        "pricing__category",
        "pricing__provider",
        "pricing__model_name",
        "pricing__sku",
        "created_at",
    ]
    search_fields = ["saved_run", "pricing"]
    readonly_fields = ["created_at"]
    ordering = ["-created_at"]

    @admin.display(description="Amount", ordering="dollar_amount")
    def display_dollar_amount(self, obj):
        return f"${obj.dollar_amount.normalize()}"

    @admin.display(description="Published Run")
    def view_parent_published_run(self, obj):
        pr = obj.saved_run.parent_published_run()
        return pr and change_obj_url(pr)

    @admin.display(description="Saved Run", ordering="saved_run")
    def view_saved_run(self, obj):
        return change_obj_url(
            obj.saved_run,
            label=f"{obj.saved_run.get_workflow_display()} - {obj.saved_run} ({obj.saved_run.run_id})",
        )

    @admin.display(description="Pricing", ordering="pricing")
    def view_pricing(self, obj):
        return change_obj_url(obj.pricing)


@admin.register(models.ModelPricing)
class ModelPricingAdmin(admin.ModelAdmin, CostQtyMixin):
    list_display = [
        "__str__",
        "cost_qty",
        "model_id",
        "category",
        "provider",
        "model_name",
        "sku",
        "view_pricing_url",
        "notes",
    ]
    list_filter = ["category", "provider", "model_name", "sku"]
    search_fields = ["category", "provider", "model_name", "sku", "model_id"]
    readonly_fields = ["created_at", "updated_at"]

    @admin.display(description="Pricing URL", ordering="pricing_url")
    def view_pricing_url(self, obj):
        return open_in_new_tab(obj.pricing_url, label=obj.pricing_url)
