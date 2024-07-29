from daras_ai_v2.settings import GCP_PROJECT, GS_BUCKET_NAME, GCS_CREDENTIALS
from django.db.models.signals import post_save
from static_pages.models import StaticPage
from django.dispatch import receiver
from google.cloud import storage
import zipfile


@receiver(post_save, sender=StaticPage)
def unzip_static_page(sender, instance, **kwargs):
    zip_file = instance.zip_file
    if instance.zip_file:
        with zipfile.ZipFile(zip_file, "r") as z:
            client = storage.Client(GCP_PROJECT, GCS_CREDENTIALS)
            bucket = client.get_bucket(GS_BUCKET_NAME)
            for file_info in z.infolist():
                if not file_info.is_dir():
                    file_data = z.read(file_info)
                    file_name = file_info.filename  # Maintain directory structure
                    blob_path = f"{instance.uid}/{file_name}"
                    blob = bucket.blob(blob_path)
                    blob.upload_from_string(file_data)
