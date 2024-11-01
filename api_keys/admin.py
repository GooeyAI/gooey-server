from django.contrib import admin

from app_users.admin import AppUserAdmin
from workspaces.admin import WorkspaceAdmin
from .models import ApiKey


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ("preview", "workspace", "created_by", "created_at")
    search_fields = (
        ["preview", "workspace__name"]
        + [f"workspace__{field}" for field in WorkspaceAdmin.search_fields]
        + [f"created_by__{field}" for field in AppUserAdmin.search_fields]
    )
    autocomplete_fields = ["workspace", "created_by"]
    readonly_fields = ["hash", "preview", "created_at", "updated_at"]
