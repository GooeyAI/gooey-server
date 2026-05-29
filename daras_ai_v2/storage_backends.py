from __future__ import annotations

import functools
import hashlib
import mimetypes
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from typing import Iterator
from urllib.parse import quote

from firebase_admin import storage as firebase_storage
from furl import furl

from daras_ai_v2 import settings

if not settings.SOVEREIGN_DEPLOY:
    from google.api_core.exceptions import NotFound as StorageNotFound
else:

    class StorageNotFound(Exception):
        pass


class FilesystemBlob:
    def __init__(self, bucket: "FilesystemBucket", name: str):
        self.bucket = bucket
        self.name = name
        self.etag: str | None = None
        self.size: int | None = None
        self.content_type: str | None = None
        self.updated: datetime | None = None

    @property
    def path(self) -> str:
        return self.name

    @property
    def public_url(self) -> str:
        base = furl(settings.APP_BASE_URL).add(path=settings.MEDIA_URL.strip("/")).url
        return f"{base}/{quote(self.name)}"

    def _full_path(self) -> Path:
        from django.conf import settings

        root = Path(settings.MEDIA_ROOT).resolve()
        full = (root / self.name).resolve()
        if not full.is_relative_to(root):
            raise ValueError(f"Path traversal detected: {self.name!r}")
        return full

    def upload_from_string(self, data: bytes, content_type: str = None):
        full_path = self._full_path()
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(data)
        self.size = len(data)
        self.etag = hashlib.md5(data).hexdigest()
        if content_type:
            self.content_type = content_type
        elif not self.content_type:
            self.content_type = mimetypes.guess_type(self.name)[0]

    def reload(self):
        full_path = self._full_path()
        if not full_path.exists():
            raise StorageNotFound(f"File not found: {self.name}")
        stat = full_path.stat()
        data = full_path.read_bytes()
        self.size = stat.st_size
        self.etag = hashlib.md5(data).hexdigest()
        self.updated = datetime.fromtimestamp(stat.st_mtime, tz=dt_timezone.utc)
        if not self.content_type:
            self.content_type = mimetypes.guess_type(self.name)[0]

    def patch(self):
        # No-op: content_type is derived from filename on the filesystem
        pass

    def delete(self):
        full_path = self._full_path()
        if not full_path.exists():
            raise StorageNotFound(f"File not found: {self.name}")
        full_path.unlink()

    def exists(self) -> bool:
        return self._full_path().exists()

    def generate_signed_url(
        self,
        version: str = None,
        expiration=None,
        method: str = "GET",
        content_type: str = None,
    ) -> str:
        if method.upper() != "GET":
            raise NotImplementedError(
                f"generate_signed_url only supports GET in filesystem mode, got {method!r}"
            )
        return self.public_url


class FilesystemBucket:
    def __init__(self, name: str):
        self.name = name

    def blob(self, path: str) -> FilesystemBlob:
        return FilesystemBlob(bucket=self, name=path)

    def list_blobs(self, prefix: str = "") -> Iterator[FilesystemBlob]:
        from django.conf import settings

        root = Path(settings.MEDIA_ROOT)

        if not root.exists():
            return

        for entry in root.rglob("*"):
            if not entry.is_file():
                continue
            rel = entry.relative_to(root)
            if prefix and not str(rel).startswith(prefix):
                continue
            blob = FilesystemBlob(bucket=self, name=str(rel))
            stat = entry.stat()
            blob.size = stat.st_size
            blob.updated = datetime.fromtimestamp(stat.st_mtime, tz=dt_timezone.utc)
            blob.content_type = mimetypes.guess_type(entry.name)[0]
            yield blob


@functools.lru_cache(maxsize=None)
def _get_filesystem_bucket(name: str) -> FilesystemBucket:
    return FilesystemBucket(name)


def get_storage_bucket(bucket_name: str = None):
    from django.conf import settings

    if not settings.SOVEREIGN_DEPLOY:
        return firebase_storage.bucket(bucket_name or settings.GS_BUCKET_NAME)
    else:
        return _get_filesystem_bucket(bucket_name or settings.GS_BUCKET_NAME)
