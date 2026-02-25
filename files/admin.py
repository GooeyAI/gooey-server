from django.contrib import admin
from django.template.defaultfilters import filesizeformat
from django.urls import reverse
from django.utils.html import format_html

from files.models import FileMetadata, UploadedFile


@admin.register(FileMetadata)
class FileMetadataAdmin(admin.ModelAdmin):
    search_fields = ("name", "etag", "mime_type")
    list_display = ("id", "name", "mime_type", "total_bytes", "etag")


@admin.register(UploadedFile)
class UploadedFileAdmin(admin.ModelAdmin):
    list_display = (
        "file_name_link",
        "metadata_mime_type",
        "metadata_size",
        "workspace_link",
        "user_link",
        "f_url_link",
        "created_at",
    )
    list_select_related = ("metadata", "workspace", "user")
    search_fields = (
        "f_url",
        "bucket_name",
        "object_name",
        "metadata__name",
        "metadata__etag",
    )
    list_filter = ("created_at", "workspace")
    readonly_fields = (
        "f_url",
        "bucket_name",
        "object_name",
        "metadata_link",
        "metadata_name",
        "metadata_mime_type",
        "metadata_size",
        "created_at",
    )
    autocomplete_fields = ("metadata", "workspace", "user")

    @admin.display(description="Name", ordering="metadata__name")
    def metadata_name(self, obj: UploadedFile):
        return obj.metadata.name

    @admin.display(description="Name", ordering="metadata__name")
    def file_name_link(self, obj: UploadedFile):
        url = reverse("admin:files_uploadedfile_change", args=[obj.pk])
        label = obj.metadata.name or f"UploadedFile #{obj.pk}"
        return format_html('<a href="{}">{}</a>', url, label)

    @admin.display(description="MIME Type", ordering="metadata__mime_type")
    def metadata_mime_type(self, obj: UploadedFile):
        return obj.metadata.mime_type

    @admin.display(description="Size", ordering="metadata__total_bytes")
    def metadata_size(self, obj: UploadedFile):
        return filesizeformat(obj.metadata.total_bytes or 0)

    @admin.display(description="Metadata")
    def metadata_link(self, obj: UploadedFile):
        if not obj.metadata_id:
            return ""
        url = reverse("admin:files_filemetadata_change", args=[obj.metadata_id])
        label = obj.metadata.name or f"FileMetadata #{obj.metadata_id}"
        return format_html('<a href="{}">{}</a>', url, label)

    @admin.display(description="Workspace", ordering="workspace")
    def workspace_link(self, obj: UploadedFile):
        if not obj.workspace_id:
            return ""
        url = reverse("admin:workspaces_workspace_change", args=[obj.workspace_id])
        return format_html('<a href="{}">{}</a>', url, obj.workspace)

    @admin.display(description="User", ordering="user")
    def user_link(self, obj: UploadedFile):
        if not obj.user_id:
            return ""
        url = reverse("admin:app_users_appuser_change", args=[obj.user_id])
        return format_html('<a href="{}">{}</a>', url, obj.user)

    @admin.display(description="File URL")
    def f_url_link(self, obj: UploadedFile):
        if not obj.f_url:
            return ""
        return format_html(
            '<a href="{0}" target="_blank" rel="noopener noreferrer">{0}</a>',
            obj.f_url,
        )
