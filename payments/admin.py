from django.contrib import admin

from gooeysite.admin import GooeyModelAdmin
from .models import SeatType, Subscription, SubscriptionSeat


class SubscriptionSeatInline(admin.TabularInline):
    model = SubscriptionSeat
    extra = 0
    autocomplete_fields = ["seat_type", "assigned_to"]
    readonly_fields = ["created_at", "updated_at"]


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
    inlines = [SubscriptionSeatInline]


@admin.register(SeatType)
class SeatTypeAdmin(GooeyModelAdmin):
    list_display = [
        "name",
        "plan",
        "monthly_charge",
        "monthly_credit_limit",
        "is_public",
        "created_at",
        "updated_at",
    ]
    list_filter = ["plan", "is_public", "created_at"]
    search_fields = ["name"]
