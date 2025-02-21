from django.contrib import admin

from workspaces.admin import WorkspaceAdmin
from .models import Handle


@admin.register(Handle)
class HandleAdmin(admin.ModelAdmin):
    search_fields = ["name", "redirect_url"] + [
        f"workspace__{field}" for field in WorkspaceAdmin.search_fields
    ]
    readonly_fields = ["workspace", "created_at", "updated_at"]

    list_filter = [
        ("workspace", admin.EmptyFieldListFilter),
        ("redirect_url", admin.EmptyFieldListFilter),
    ]
