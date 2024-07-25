from django.contrib import admin
from django.db import models
from django.utils import timezone

from bots.custom_fields import CustomURLField
from daras_ai_v2.embedding_model import EmbeddingModels


class EmbeddedFile(models.Model):
    created_by = models.ForeignKey(
        "app_users.AppUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        default=None,
        related_name="embedded_files",
    )

    url = CustomURLField(help_text="The URL of the original resource (e.g. a document)")
    metadata = models.ForeignKey(
        "files.FileMetadata",
        on_delete=models.CASCADE,
        related_name="embedded_files",
    )
    max_context_words = models.PositiveSmallIntegerField()
    scroll_jump = models.PositiveSmallIntegerField()
    google_translate_target = models.CharField(max_length=5, blank=True)
    selected_asr_model = models.CharField(max_length=100, blank=True)
    embedding_model = models.CharField(
        max_length=100,
        choices=[(model.name, model.label) for model in EmbeddingModels],
        default=EmbeddingModels.openai_3_large.name,
    )

    vespa_file_id = models.CharField(
        max_length=64,
        unique=True,
        help_text="The ID of this file in Vespa. A hash of the file's metadata.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    query_count = models.PositiveIntegerField(default=0, db_index=True)
    last_query_at = models.DateTimeField(
        null=True, blank=True, default=None, db_index=True
    )

    def __str__(self):
        return f"{self.url} ({self.metadata})"

    class Meta:
        indexes = [
            models.Index(
                fields=[
                    "url",
                    "metadata",
                    "max_context_words",
                    "scroll_jump",
                    "google_translate_target",
                    "selected_asr_model",
                    "embedding_model",
                    "-updated_at",
                ]
            ),
            models.Index(fields=["-updated_at"]),
        ]


class EmbeddingsReference(models.Model):
    embedded_file = models.ForeignKey(
        "EmbeddedFile",
        on_delete=models.CASCADE,
        related_name="embeddings_references",
    )
    vespa_doc_id = models.CharField(
        max_length=256,
        help_text="The Document ID of this embedding in Vespa. A hash of the file metadata + the split snippet.",
    )
    url = CustomURLField()
    title = models.TextField()
    snippet = models.TextField()

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["-updated_at"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.url})"

    @admin.display(description="Metadata")
    def metadata(self):
        return self.embedded_file.metadata
