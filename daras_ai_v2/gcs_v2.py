from __future__ import annotations
import datetime
import os
import typing

if typing.TYPE_CHECKING:
    from firebase_admin import storage


GCS_BASE_URL = "https://storage.googleapis.com"
GCS_BUCKET_NAME = "gooey.ai"
GCS_BUCKET_URL = os.path.join(GCS_BASE_URL, GCS_BUCKET_NAME)


def private_to_signed_url(url: str) -> str:
    blob = private_url_to_blob(url)
    if blob is None:
        return url
    return blob.generate_signed_url(
        version="v4", expiration=datetime.timedelta(minutes=60)
    )


def update_content_type(url: str, content_type: str):
    blob = private_url_to_blob(url)
    if blob is None or (
        blob.content_type and blob.content_type not in dumb_content_types
    ):
        return
    blob.content_type = content_type
    blob.patch()


dumb_content_types = ["application/octet-stream", "application/x-www-form-urlencoded"]


def private_url_to_blob(url: str) -> storage.Blob | None:
    from firebase_admin import storage

    if not url.startswith(GCS_BUCKET_URL):
        return None
    return storage.bucket(GCS_BUCKET_NAME).blob(
        url.removeprefix(GCS_BUCKET_URL).strip("/")
    )
