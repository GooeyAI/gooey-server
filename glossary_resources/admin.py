from django.contrib import admin
from .models import GlossaryResource


# Register your models here.
@admin.register(GlossaryResource)
class GlossaryAdmin(admin.ModelAdmin):
    list_display = ["f_url", "usage_count", "last_updated", "glossary_id"]
    list_filter = ["usage_count", "last_updated"]
    search_fields = ["f_url", "glossary_name"]
    ordering = ["-usage_count", "-last_updated"]
