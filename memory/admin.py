from django.contrib import admin

from django.db import models
from gooeysite.custom_widgets import JSONEditorWidget
from memory.models import MemoryEntry


@admin.register(MemoryEntry)
class MemoryEntryAdmin(admin.ModelAdmin):
    list_display = (
        "user_id",
        "key",
        "saved_run",
        "created_at",
        "updated_at",
    )
    search_fields = ("user_id", "key", "value")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("saved_run",)

    formfield_overrides = {
        models.JSONField: {"widget": JSONEditorWidget},
    }
