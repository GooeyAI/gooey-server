from django.contrib import admin

from cms.models import (
    NewsItem,
    WorkflowCard,
    WorkflowTab,
)
from gooeysite.admin import GooeyModelAdmin


class WorkflowCardInline(admin.TabularInline):
    model = WorkflowCard
    fields = ["priority", "workflow"]
    extra = 1
    autocomplete_fields = ["workflow"]


@admin.register(WorkflowTab)
class WorkflowTabAdmin(GooeyModelAdmin):
    list_display = ["tab_title", "priority"]
    fields = ["workflow_metadata", "priority"]
    autocomplete_fields = ["workflow_metadata"]
    inlines = [WorkflowCardInline]
    search_fields = ["workflow_metadata__short_title", "workflow_metadata__meta_title"]

    @admin.display(description="Title")
    def tab_title(self, obj):
        return obj.workflow_metadata.short_title


@admin.register(NewsItem)
class NewsItemAdmin(GooeyModelAdmin):
    list_display = ["publish_date", "headline", "tag"]
    list_filter = ["tag"]
    search_fields = ["headline", "tag"]
    date_hierarchy = "publish_date"
    fields = ["publish_date", "headline", "tag", "photo_url", "url"]
