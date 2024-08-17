from django.contrib import admin

from .models import Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    search_fields = [
        "plan",
        "payment_provider",
        "external_id",
    ]
    readonly_fields = [
        "created_at",
        "updated_at",
        "get_payment_method_summary",
    ]
