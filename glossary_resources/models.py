import uuid

from django.db import models, IntegrityError, transaction

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
    doc_url_to_file_metadata,
)
from daras_ai_v2.vector_search import (
    download_content_bytes,
    tabular_bytes_to_str_df,
)
from files.models import FileMetadata


class GlossaryResourceQuerySet(models.QuerySet):
    def get_or_create_from_url(self, url: str) -> tuple["GlossaryResource", bool]:
        metadata = doc_url_to_file_metadata(url)
        try:
            return (
                GlossaryResource.objects.get(
                    f_url=url,
                    metadata__name=metadata.name,
                    metadata__etag=metadata.etag,
                    metadata__mime_type=metadata.mime_type,
                    metadata__total_bytes=metadata.total_bytes,
                ),
                False,
            )
        except GlossaryResource.DoesNotExist:
            try:
                gr = create_glossary_cached(
                    url=url,
                    name=metadata.name,
                    etag=metadata.etag,
                    mime_type=metadata.mime_type,
                )
                with transaction.atomic():
                    try:
                        gr.id = GlossaryResource.objects.get(f_url=url).id
                    except GlossaryResource.DoesNotExist:
                        pass
                    metadata.save()
                    gr.metadata = metadata
                    gr.save()
                    return gr, True
            except IntegrityError:
                try:
                    return GlossaryResource.objects.get(f_url=url), False
                except self.model.DoesNotExist:
                    pass
                raise


@redis_cache_decorator
def create_glossary_cached(
    *,
    url: str,
    name: str,
    etag: str | None,
    mime_type: str | None,
) -> "GlossaryResource":
    f_bytes, mime_type = download_content_bytes(f_url=url, mime_type=mime_type)
    df = tabular_bytes_to_str_df(f_name=name, f_bytes=f_bytes, mime_type=mime_type)
    if is_user_uploaded_url(url):
        glossary_url = url
    else:
        glossary_url = upload_file_from_bytes(
            name + ".csv",
            df.to_csv(index=False).encode(),
            content_type="text/csv",
        )
    gr = GlossaryResource(
        f_url=url,
        language_codes=get_langcodes_from_df(df),
        project_id=settings.GCP_PROJECT,
        location=settings.GCP_REGION,
        glossary_url=glossary_url,
    )
    create_glossary(
        language_codes=gr.language_codes,
        input_uri=gs_url_to_uri(gr.glossary_url),
        project_id=gr.project_id,
        location=gr.location,
        glossary_name=gr.glossary_name,
    )
    return gr


class GlossaryResource(models.Model):
    f_url = CustomURLField(unique=True, verbose_name="File URL")
    metadata = models.ForeignKey(
        "files.FileMetadata",
        on_delete=models.CASCADE,
        related_name="glossary_resources",
    )

    language_codes = models.JSONField(default=list)
    glossary_url = CustomURLField()
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
