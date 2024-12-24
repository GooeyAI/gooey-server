from django.contrib import admin

from managed_secrets.models import ManagedSecret


@admin.register(ManagedSecret)
class ManagedSecretAdmin(admin.ModelAdmin):
    list_display = [
        "__str__",
        "workspace",
        "created_at",
        "updated_at",
        "usage_count",
        "last_used_at",
    ]
    autocomplete_fields = ["workspace", "created_by"]
    readonly_fields = ["usage_count", "last_used_at", "external_id"]
    search_fields = ["name", "external_id"]
