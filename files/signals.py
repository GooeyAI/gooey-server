from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from daras_ai_v2.storage_backends import get_storage_bucket, StorageNotFound
from loguru import logger

from files.models import UploadedFile


@receiver(post_delete, sender=UploadedFile)
def delete_uploaded_file_blob(sender, instance: UploadedFile, **kwargs):
    def _delete_blob():
        try:
            bucket = get_storage_bucket(instance.bucket_name)
            blob = bucket.blob(instance.object_name)
            blob.delete()
        except StorageNotFound:
            logger.info(
                "GCS object not found for UploadedFile id={id} bucket={bucket} object={object}",
                id=instance.id,
                bucket=instance.bucket_name,
                object=instance.object_name,
            )

    transaction.on_commit(_delete_blob)
