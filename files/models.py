from django.db import models
from django.template.defaultfilters import filesizeformat
from loguru import logger


class FileMetadata(models.Model):
    name = models.TextField(default="", blank=True)
    etag = models.CharField(max_length=255, null=True)
    mime_type = models.CharField(max_length=255, default="", blank=True)
    total_bytes = models.PositiveIntegerField(default=0, blank=True)

    export_links: dict[str, str] | None = None

    def __str__(self):
        ret = f"{self.name or 'Unnamed'} - {self.mime_type}"
        if self.total_bytes:
            ret += f" - {filesizeformat(self.total_bytes)}"
        if self.etag:
            ret += f" - {self.etag}"
        return ret

    def __eq__(self, other):
        ret = bool(
            isinstance(other, FileMetadata)
            # avoid null comparisions -- when metadata is not available and hence not comparable
            and (self.etag or other.etag or self.total_bytes or other.total_bytes)
            and self.astuple() == other.astuple()
        )
        logger.debug(f"checking: `{self}` == `{other}` ({ret})")
        return ret

    def astuple(self) -> tuple:
        return self.name, self.etag, self.mime_type, self.total_bytes

    class Meta:
        indexes = [
            models.Index(fields=["name", "etag", "mime_type", "total_bytes"]),
        ]
