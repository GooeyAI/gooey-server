from django.contrib import admin

from .models import BotExtension, BotExtensionUser, ProvisionedNumber


@admin.register(BotExtension)
class BotExtensionAdmin(admin.ModelAdmin):
    list_display = ("extension_number", "bot_integration", "created_at", "updated_at")
    list_filter = ("bot_integration", "created_at")
    search_fields = ("extension_number", "bot_integration__name")
    autocomplete_fields = ("bot_integration",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(BotExtensionUser)
class BotExtensionUserAdmin(admin.ModelAdmin):
    list_display = ("extension", "wa_phone_number", "twilio_phone_number", "created_at")
    list_filter = ("extension__bot_integration", "created_at")
    search_fields = (
        "wa_phone_number",
        "twilio_phone_number",
        "extension__extension_number",
    )
    autocomplete_fields = ("extension",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(ProvisionedNumber)
class ProvisionedNumberAdmin(admin.ModelAdmin):
    list_display = ("phone_number", "platform", "is_active", "created_at")
    list_filter = ("platform", "is_active", "created_at")
    search_fields = ("phone_number", "notes")
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "phone_number",
        "platform",
        "wa_phone_number_id",
        "is_active",
        "notes",
        "created_at",
        "updated_at",
    )
