from django.contrib import admin

from gooeysite.admin import GooeyModelAdmin
from .models import Subscription


@admin.register(Subscription)
class SubscriptionAdmin(GooeyModelAdmin):
    search_fields = [
        "plan",
        "payment_provider",
        "external_id",
    ]
    readonly_fields = [
        "user",
        "created_at",
        "updated_at",
        "get_payment_method_summary",
    ]
