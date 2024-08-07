from django.contrib import admin

from bots.admin_links import list_related_html_url
from embeddings.models import EmbeddingsReference, EmbeddedFile


@admin.register(EmbeddedFile)
class EmbeddedFileAdmin(admin.ModelAdmin):
    list_display = [
        "url",
        "metadata",
        "max_context_words",
        "scroll_jump",
        "embedding_model",
        "google_translate_target",
        "selected_asr_model",
        "vespa_file_id",
        "query_count",
        "created_at",
        "last_query_at",
    ]
    search_fields = [
        "url",
        "metadata__name",
        "metadata__etag",
        "metadata__mime_type",
        "vespa_file_id",
    ]
    list_filter = [
        "metadata__mime_type",
        "embedding_model",
        "google_translate_target",
        "selected_asr_model",
        "created_at",
        "updated_at",
        "last_query_at",
    ]
    readonly_fields = [
        "metadata",
        "vespa_file_id",
        "created_at",
        "updated_at",
        "view_embeds",
        "query_count",
        "last_query_at",
    ]
    autocomplete_fields = ["created_by"]
    ordering = ["-created_at"]

    @admin.display(description="View Embeds")
    def view_embeds(self, obj: EmbeddedFile):
        return list_related_html_url(obj.embeddings_references)


@admin.register(EmbeddingsReference)
class EmbeddingsReferenceAdmin(admin.ModelAdmin):
    list_display = ["url", "title", "metadata", "vespa_doc_id", "created_at"]
    search_fields = ["embedded_file__url", "title", "snippet", "vespa_doc_id"]
    readonly_fields = ["vespa_doc_id", "created_at", "updated_at"]
    autocomplete_fields = ["embedded_file"]
    ordering = ["-created_at"]
