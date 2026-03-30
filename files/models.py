from django.db import models
from django.template.defaultfilters import filesizeformat
from loguru import logger

from bots.custom_fields import CustomURLField


class FileMetadata(models.Model):
    name = models.TextField(default="", blank=True)
    etag = models.CharField(max_length=255, null=True)
    mime_type = models.CharField(max_length=255, default="", blank=True)
    total_bytes = models.PositiveIntegerField(default=0, blank=True)

    export_links: dict[str, str] | None = None
    ref_data: dict | None = None

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


class UploadedFile(models.Model):
    metadata = models.ForeignKey(
        "files.FileMetadata",
        on_delete=models.CASCADE,
        related_name="uploaded_files",
    )
    f_url = CustomURLField(unique=True, verbose_name="File URL")
    bucket_name = models.CharField(max_length=255)
    object_name = models.TextField()
    saved_run = models.ForeignKey(
        "bots.SavedRun",
        on_delete=models.SET_NULL,
        related_name="uploaded_files",
        null=True,
        blank=True,
    )
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.SET_NULL,
        related_name="uploaded_files",
        null=True,
        blank=True,
    )
    user = models.ForeignKey(
        "app_users.AppUser",
        on_delete=models.SET_NULL,
        related_name="uploaded_files",
        null=True,
        blank=True,
    )
    is_user_uploaded = models.BooleanField(default=False)
    is_uploading = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["workspace", "created_at"],
                name="files_uploa_workspa_3d4b4a_idx",
            ),
            models.Index(
                fields=["user", "created_at"],
                name="files_uploa_user_id_7bdbf8_idx",
            ),
            models.Index(
                fields=["created_at"],
                name="files_uploa_created_5e3e16_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["bucket_name", "object_name"],
                name="uploadedfile_bucket_object_unique",
            ),
        ]
