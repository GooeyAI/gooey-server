import json

from django.contrib import admin
from django.template import loader
from django.utils.safestring import mark_safe

from app_users.admin import AppUserAdmin
from bots.admin import SavedRunAdmin
from bots.admin_links import list_related_html_url
from gooeysite.custom_actions import export_to_csv, export_to_excel
from gooeysite.custom_filters import (
    json_field_nested_lookup_keys,
    related_json_field_summary,
)
from url_shortener import models

JSON_FIELDS = ["browser", "device", "os", "ip_data"]

EXCLUDE_KEYS = {
    "version",
    "version_string",
    "ip",
    "start",
    "end",
    "code",
    "count",
    "route",
}


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
        "created_at",
        "updated_at",
        "shortened_url",
        "get_saved_runs",
        "clicks",
        "view_visitors",
        "view_visitor_summary",
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

    @admin.display(description="Visitors")
    def view_visitors(self, obj: models.ShortenedURL):
        return list_related_html_url(obj.visitors, instance_id=obj.pk)

    @admin.display(description="Visitor Summary")
    def view_visitor_summary(self, surl: models.ShortenedURL):
        html = ""
        for field in JSON_FIELDS:
            results = related_json_field_summary(
                surl.visitors, field, exclude_keys=EXCLUDE_KEYS
            )
            html += "<h2>" + field.replace("_", " ").capitalize() + "</h2>"
            html += loader.render_to_string(
                "anaylsis_result.html", context=dict(results=results)
            )
        html = mark_safe(html)
        return html


def jsonfieldlistfilter(field: str):
    class JSONFieldListFilter(admin.SimpleListFilter):
        title = field.replace("_", " ").capitalize()
        parameter_name = field

        def lookups(self, request, model_admin):
            qs = model_admin.model.objects.all()
            lookups = json_field_nested_lookup_keys(
                qs, field, exclude_keys=EXCLUDE_KEYS
            )
            return [
                (
                    json.dumps([k, v]),
                    f'{k.split(field + "__")[-1]} = {v}',
                )
                for k in lookups
                for v in qs.values_list(k, flat=True).distinct()
            ]

        def queryset(self, request, queryset):
            val = self.value()
            if val is None:
                return queryset
            k, v = json.loads(val)
            return queryset.filter(**{k: v})

    return JSONFieldListFilter


@admin.register(models.VisitorClickInfo)
class VisitorClickInfoAdmin(admin.ModelAdmin):
    list_filter = [
        "created_at",
    ] + [jsonfieldlistfilter(name) for name in JSON_FIELDS]
    search_fields = ["ip_address", "user_agent", "ip_data"] + [
        f"shortened_url__{field}" for field in ShortenedURLAdmin.search_fields
    ]
    list_display = [
        "__str__",
        "user_agent",
        "ip_data",
        "created_at",
    ]
    ordering = ["created_at"]
    autocomplete_fields = ["shortened_url"]
    actions = [export_to_csv, export_to_excel]
