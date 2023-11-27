from django.db import models
from django.template.defaultfilters import filesizeformat


class FileMetadata(models.Model):
    name = models.TextField(default="", blank=True)
    etag = models.CharField(max_length=255, null=True)
    mime_type = models.CharField(max_length=255, default="", blank=True)
    total_bytes = models.PositiveIntegerField(default=0, blank=True)

    def __str__(self):
        ret = f"{self.name or self.etag} ({self.mime_type})"
        if self.total_bytes:
            ret += f" - {filesizeformat(self.total_bytes)}"
        return ret
