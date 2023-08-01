from django.contrib import admin

from bots.admin import SavedRunAdmin, export_to_csv, export_to_excel
from bots.admin_links import list_related_html_url
from url_shortener import models

from app_users.admin import AppUserAdmin


@admin.register(models.ShortenedURL)
class ShortenedURLAdmin(admin.ModelAdmin):
    autocomplete_fields = ["user"]
    list_filter = [
        "clicks",
        "created_at",
    ]
    search_fields = (
        ["url"]
        + [f"saved_runs__{field}" for field in SavedRunAdmin.search_fields]
        + [f"user__{field}" for field in AppUserAdmin.search_fields]
    )
    list_display = [
        "url",
        "user",
        "shortened_url",
        "clicks",
        "get_max_clicks",
        "disabled",
        "created_at",
        "updated_at",
    ]
    readonly_fields = [
        "clicks",
        "created_at",
        "updated_at",
        "shortened_url",
        "get_saved_runs",
    ]
    exclude = ["saved_runs"]
    ordering = ["created_at"]
    actions = [export_to_csv, export_to_excel]

    @admin.display(ordering="max_clicks", description="Max Clicks")
    def get_max_clicks(self, obj):
        max_clicks = obj.max_clicks
        return max_clicks or "∞"

    @admin.display(description="Saved Runs")
    def get_saved_runs(self, obj: models.ShortenedURL):
        return list_related_html_url(obj.saved_runs, show_add=False)
