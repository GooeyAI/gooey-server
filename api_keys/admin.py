from django.contrib import admin

from .models import ApiKey


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ("preview", "workspace", "created_by", "created_at")
    search_fields = [
        "preview",
        "workspace__name",
        "created_by__display_name",
        "created_by__email",
        "created_by__uid",
    ]
