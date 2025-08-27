import typing
from datetime import timedelta

from django.utils import timezone

from daras_ai_v2 import settings
from daras_ai_v2.vector_search import get_vespa_app
from embeddings.models import EmbeddedFile

if typing.TYPE_CHECKING:
    from vespa.io import VespaResponse


STALENESS_THRESHOLD_DAYS = 90
BATCH_SIZE = 1_000


def cleanup_stale_cache():
    vespa = get_vespa_app()

    while True:
        stale_files = EmbeddedFile.objects.prefetch_related(
            "embeddings_references"
        ).filter(
            updated_at__lt=timezone.now() - timedelta(days=STALENESS_THRESHOLD_DAYS)
        )[:BATCH_SIZE]
        if not stale_files:
            break

        docs_to_delete = (
            {"id": ref.vespa_doc_id}
            for ef in stale_files
            for ref in ef.embeddings_references.all()
        )
        if docs_to_delete:
            total_deleted = 0

            def vespa_callback(response: "VespaResponse", id: str):
                nonlocal total_deleted
                if response.is_successful():
                    total_deleted += 1
                else:
                    print(
                        f"Failed to delete document {id} from Vespa: {getattr(response,'status_code', 'NA')} - {response.get_json()}"
                    )
            vespa.feed_iterable(
                docs_to_delete,
                schema=settings.VESPA_SCHEMA,
                operation_type="delete",
                callback=vespa_callback,
            )
            print(f"Deleted {total_deleted} documents from Vespa.")

        deleted_per_model = EmbeddedFile.objects.filter(
            id__in=[ef.id for ef in stale_files]
        ).delete()
        print(f"Deleted EmbeddedFiles & related objects: {deleted_per_model}")


def run():
    cleanup_stale_cache()
