from django.contrib import admin
from .models import StaticPage


@admin.register(StaticPage)
class StaticPageAdmin(admin.ModelAdmin):
    fieldsets = [
        (
            None,
            {
                "fields": [
                    "uid",
                    "name",
                    "path",
                    "zip_file",
                    "created_at",
                    "updated_at",
                    "disable_page_wrapper",
                ],
            },
        ),
    ]
    list_display = [
        "name",
        "path",
        "created_at",
        "updated_at",
        "disable_page_wrapper",
    ]
    list_filter = ["created_at", "updated_at", "disable_page_wrapper"]
    search_fields = ["name", "path"]
    readonly_fields = ["uid", "created_at", "updated_at"]
    ordering = ["-updated_at"]
