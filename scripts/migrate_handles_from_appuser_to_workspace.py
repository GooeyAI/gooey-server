from django.db.models import OuterRef

from app_users.models import AppUser
from workspaces.models import Workspace
from .migrate_workspaces import update_in_batches


def run():
    migrate_handles()
    cleanup_handles()


def migrate_handles():
    qs = Workspace.objects.filter(
        is_personal=True,
        handle_id__isnull=True,
        created_by__handle_id__isnull=False,
    )
    update_in_batches(
        qs,
        handle_id=AppUser.objects.filter(id=OuterRef("created_by_id")).values(
            "handle_id"
        )[:1],
    )


def cleanup_handles():
    qs = AppUser.objects.filter(handle__workspace__isnull=False)
    update_in_batches(qs, handle=None)
