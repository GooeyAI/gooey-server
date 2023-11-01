import uuid

from django.db import models, IntegrityError, transaction

from app_users.models import FileMetadata
from bots.custom_fields import CustomURLField
from daras_ai.image_input import gs_url_to_uri, upload_file_from_bytes
from daras_ai_v2 import settings
from daras_ai_v2.doc_search_settings_widgets import is_user_uploaded_url
from daras_ai_v2.glossary import (
    get_langcodes_from_df,
    create_glossary,
)
from daras_ai_v2.redis_cache import redis_cache_decorator
from daras_ai_v2.vector_search import (
    doc_url_to_metadata,
)
from daras_ai_v2.vector_search import (
    download_content_bytes,
    bytes_to_df,
    DocMetadata,
)


class GlossaryResourceQuerySet(models.QuerySet):
    def get_or_create_from_url(self, url: str) -> tuple["GlossaryResource", bool]:
        doc_meta = doc_url_to_metadata(url)
        try:
            gr = GlossaryResource.objects.get(f_url=url)
            GlossaryResource.objects.filter(pk=gr.pk).update(
                usage_count=models.F("usage_count") + 1
            )
            return gr, False
        except GlossaryResource.DoesNotExist:
            try:
                gr = create_glossary_cached(url, doc_meta)
                with transaction.atomic():
                    try:
                        gr.id = GlossaryResource.objects.get(f_url=url).id
                    except GlossaryResource.DoesNotExist:
                        pass
                    gr.metadata = FileMetadata.objects.create(
                        name=doc_meta.name,
                        etag=doc_meta.etag,
                        mime_type=doc_meta.mime_type,
                    )
                    gr.save()
                    return gr, True
            except IntegrityError:
                try:
                    return GlossaryResource.objects.get(f_url=url), False
                except self.model.DoesNotExist:
                    pass
                raise


@redis_cache_decorator
def create_glossary_cached(url: str, doc_meta: DocMetadata) -> "GlossaryResource":
    f_bytes, ext = download_content_bytes(f_url=url, mime_type=doc_meta.name)
    df = bytes_to_df(f_name=doc_meta.name, f_bytes=f_bytes, ext=ext)
    if not is_user_uploaded_url(url):
        url = upload_file_from_bytes(
            doc_meta.name + ".csv",
            df.to_csv(index=False).encode(),
            content_type="text/csv",
        )
    gr = GlossaryResource(
        f_url=url,
        language_codes=get_langcodes_from_df(df),
        project_id=settings.GCP_PROJECT,
        location=settings.GCP_REGION,
        glossary_uri=gs_url_to_uri(url),
    )
    create_glossary(
        language_codes=gr.language_codes,
        input_uri=gr.glossary_uri,
        project_id=gr.project_id,
        location=gr.location,
        glossary_name=gr.glossary_name,
    )
    return gr


class GlossaryResource(models.Model):
    f_url = CustomURLField(unique=True)
    metadata = models.ForeignKey(
        "app_users.FileMetadata",
        on_delete=models.CASCADE,
        related_name="glossary_resources",
    )

    language_codes = models.JSONField()
    glossary_uri = models.TextField()
    glossary_id = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    project_id = models.CharField(max_length=100, default=settings.GCP_PROJECT)
    location = models.CharField(max_length=100, default=settings.GCP_REGION)

    usage_count = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)

    objects = GlossaryResourceQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=["usage_count", "last_updated"]),
        ]

    def __str__(self):
        return f"{self.metadata.name or self.f_url} ({self.glossary_id})"

    def get_glossary_path(self) -> dict:
        from google.cloud import translate_v3 as translate

        client = translate.TranslationServiceClient()
        return client.glossary_path(self.project_id, self.location, self.glossary_name)

    @property
    def glossary_name(self) -> str:
        return f"gooey-api--{self.glossary_id}"
