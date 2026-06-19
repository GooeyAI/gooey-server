from django.contrib import admin

from cms.models import NewsItem
from gooeysite.admin import GooeyModelAdmin


@admin.register(NewsItem)
class NewsItemAdmin(GooeyModelAdmin):
    list_display = ["publish_date", "headline", "tag"]
    list_filter = ["tag"]
    search_fields = ["headline", "tag"]
    date_hierarchy = "publish_date"
    fields = ["publish_date", "headline", "tag", "photo_url", "url"]
