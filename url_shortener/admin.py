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
        "use_analytics",
    ]
    readonly_fields = [
        "clicks",
        "created_at",
        "updated_at",
        "shortened_url",
        "get_saved_runs",
        "get_click_analytics",
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

    @admin.display(description="Analytic Clicks")
    def get_click_analytics(self, obj: models.ShortenedURL):
        if not obj.use_analytics:
            return []
        return list_related_html_url(
            models.ClickAnalytic.objects.filter(shortened_url__pk=obj.pk),
            query_param="shortened_url__id__exact",
            instance_id=obj.pk,
            show_add=False,
        )


@admin.register(models.ClickAnalytic)
class ClickAnalyticAdmin(admin.ModelAdmin):
    list_filter = [
        "shortened_url__url",
        "created_at",
    ]
    search_fields = (
        ["ip_address"]
        + [
            f"shortened_url__saved_runs__{field}"
            for field in SavedRunAdmin.search_fields
        ]
        + [f"shortened_url__user__{field}" for field in AppUserAdmin.search_fields]
        + [f"shortened_url__{field}" for field in ShortenedURLAdmin.search_fields]
    )
    list_display = [
        "ip_address",
        "platform",
        "operating_system",
        "device_model",
        "country_name",
        "city_name",
        "created_at",
        "location_data",
        "user_agent",
        "get_saved_runs",
    ]
    readonly_fields = [
        "ip_address",
        "platform",
        "operating_system",
        "device_model",
        "country_name",
        "city_name",
        "created_at",
        "location_data",
        "user_agent",
    ]
    exclude = ["saved_runs"]
    ordering = ["created_at"]
    actions = [export_to_csv, export_to_excel]

    @admin.display(description="Saved Runs")
    def get_saved_runs(self, obj: models.ClickAnalytic):
        return list_related_html_url(obj.shortened_url.saved_runs, show_add=False)
