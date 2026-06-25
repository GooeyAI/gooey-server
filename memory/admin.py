from django.contrib import admin

from django.db import models
from gooeysite.admin import GooeyModelAdmin
from gooeysite.custom_widgets import JSONEditorWidget
from memory.models import MemoryEntry


@admin.register(MemoryEntry)
class MemoryEntryAdmin(GooeyModelAdmin):
    list_display = (
        "user_id",
        "key",
        "created_at",
        "updated_at",
    )
    list_filter = ("scope", "updated_at")
    search_fields = ("user_id", "key", "value")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = (
        "saved_run",
        "workspace",
        "member",
        "saved_workflow",
        "deployment",
        "conversation",
    )

    formfield_overrides = {
        models.JSONField: {"widget": JSONEditorWidget},
    }
