from django.contrib import admin

from bots.admin_links import change_obj_url, open_in_new_tab
from files.models import FileMetadata, UploadedFile


@admin.register(FileMetadata)
class FileMetadataAdmin(admin.ModelAdmin):
    search_fields = ("name", "etag", "mime_type")
    list_display = ("__str__", "name", "mime_type", "total_bytes", "etag")


@admin.register(UploadedFile)
class UploadedFileAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
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
    list_filter = ("created_at",)
    readonly_fields = (
        "f_url_link",
        "bucket_name",
        "object_name",
        "metadata_link",
        "created_at",
    )
    autocomplete_fields = ("metadata", "saved_run", "workspace", "user")

    @admin.display(description="Metadata")
    def metadata_link(self, obj: UploadedFile):
        return obj.metadata_id and change_obj_url(obj.metadata)

    @admin.display(description="Workspace", ordering="workspace")
    def workspace_link(self, obj: UploadedFile):
        return obj.workspace_id and change_obj_url(obj.workspace)

    @admin.display(description="User", ordering="user")
    def user_link(self, obj: UploadedFile):
        return obj.user_id and change_obj_url(obj.user)

    @admin.display(description="File URL")
    def f_url_link(self, obj: UploadedFile):
        return open_in_new_tab(obj.f_url, label=obj.f_url)
