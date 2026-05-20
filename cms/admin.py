from django.contrib import admin

from cms.models import (
    IndustryTile,
    NewsItem,
    WorkflowCard,
    WorkflowTab,
)
from gooeysite.admin import GooeyModelAdmin


class WorkflowCardInline(admin.TabularInline):
    model = WorkflowCard
    fields = ["order", "recipe"]
    extra = 1
    autocomplete_fields = ["recipe"]


@admin.register(WorkflowTab)
class WorkflowTabAdmin(GooeyModelAdmin):
    list_display = ["title", "order"]
    fields = ["title", "icon", "order"]
    inlines = [WorkflowCardInline]
    search_fields = ["title"]


@admin.register(IndustryTile)
class IndustryTileAdmin(GooeyModelAdmin):
    list_display = ["tag", "order"]
    fields = ["tag", "order"]
    search_fields = ["tag__name"]
    autocomplete_fields = ["tag"]


@admin.register(NewsItem)
class NewsItemAdmin(GooeyModelAdmin):
    list_display = ["publish_date", "headline", "tag"]
    list_filter = ["tag"]
    search_fields = ["headline", "tag"]
    date_hierarchy = "publish_date"
    fields = ["publish_date", "headline", "tag", "photo_url", "url"]
