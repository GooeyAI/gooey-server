from django.contrib import admin

from app_users.admin import AppUserAdmin
from workspaces.admin import WorkspaceAdmin
from .models import Handle


@admin.register(Handle)
class HandleAdmin(admin.ModelAdmin):
    search_fields = (
        ["name", "redirect_url"]
        + [f"user__{field}" for field in AppUserAdmin.search_fields]
        + [f"workspace__{field}" for field in WorkspaceAdmin.search_fields]
    )
    readonly_fields = ["user", "workspace", "created_at", "updated_at"]

    list_filter = [
        ("user", admin.EmptyFieldListFilter),
        ("workspace", admin.EmptyFieldListFilter),
        ("redirect_url", admin.EmptyFieldListFilter),
    ]
