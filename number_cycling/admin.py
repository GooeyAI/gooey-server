from django import forms
from django.contrib import admin

from bots.admin import BotIntegrationAdmin
from bots.admin_links import list_related_html_url
from bots.models import BotIntegration
from number_cycling.models import SharedPhoneNumber, SharedPhoneNumberBotUser


@admin.register(SharedPhoneNumber)
class SharedPhoneNumberAdmin(admin.ModelAdmin):
    search_fields = [
        "wa_phone_number",
        "wa_phone_number_id",
        "twilio_phone_number",
        "twilio_phone_number_sid",
        "notes",
    ]
    list_display = ["__str__", "platform", "updated_at"]
    list_filter = ["platform"]
    readonly_fields = [
        "view_users",
        "view_bots",
        "created_at",
        "updated_at",
    ]

    @admin.display(description="Users")
    def view_users(self, obj: SharedPhoneNumber):
        return list_related_html_url(obj.users, show_add=False)

    @admin.display(description="Bots")
    def view_bots(self, obj: SharedPhoneNumber):
        return list_related_html_url(obj.bot_integrations, show_add=False)


@admin.register(SharedPhoneNumberBotUser)
class SharedPhoneNumberBotUserAdmin(admin.ModelAdmin):
    autocomplete_fields = ["shared_phone_number", "bot_integration"]
    readonly_fields = [
        "created_at",
        "updated_at",
    ]
    search_fields = (
        [
            "wa_phone_number",
            "twilio_phone_number",
        ]
        + [f"bot_integration__{field}" for field in BotIntegrationAdmin.search_fields]
        + [
            f"shared_phone_number__{field}"
            for field in SharedPhoneNumberAdmin.search_fields
        ]
    )
    list_display = ["__str__", "updated_at"]
