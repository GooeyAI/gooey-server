from django.db import transaction
from django.db.models import OuterRef

from app_users.models import AppUser, AppUserTransaction
from bots.models import SavedRun, PublishedRun
from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole


@transaction.atomic
def run():
    migrate_personal_workspaces()
    migrate_txns()
    migrate_saved_runs()
    ## LATER
    # migrate_published_runs()


def migrate_personal_workspaces():
    users = AppUser.objects.exclude(workspace_memberships__workspace__is_personal=True)
    workspaces = [
        Workspace(
            created_by=user,
            is_personal=True,
            balance=user.balance,
            stripe_customer_id=user.stripe_customer_id,
            subscription=user.subscription,
            low_balance_email_sent_at=user.low_balance_email_sent_at,
            is_paying=user.is_paying,
        )
        for user in users
    ]
    memberships = [
        WorkspaceMembership(
            workspace=workspace,
            user=user,
            role=WorkspaceRole.OWNER,
        )
        for user, workspace in zip(users, workspaces)
    ]
    print(f"creating {len(workspaces)} workspaces...")
    Workspace.objects.bulk_create(workspaces)
    WorkspaceMembership.objects.bulk_create(memberships)


def migrate_txns():
    qs = AppUserTransaction.objects.filter(workspace__isnull=True)
    print(f"migrating {qs.count()} txns...")
    rows = qs.update(
        workspace_id=Workspace.objects.filter(
            is_personal=True,
            created_by_id=OuterRef("user_id"),
        ).values("id")[:1]
    )
    print(f"updated {rows} txns")


def migrate_saved_runs():
    qs = SavedRun.objects.filter(workspace__isnull=True, uid__isnull=False).exclude(
        uid=""
    )
    print(f"migrating {qs.count()} saved runs...")
    rows = qs.update(
        workspace_id=Workspace.objects.filter(
            is_personal=True,
            created_by__uid=OuterRef("uid"),
        ).values("id")[:1]
    )
    print(f"updated {rows} saved runs")


def migrate_published_runs():
    qs = PublishedRun.objects.filter(workspace__isnull=True, created_by__isnull=False)
    print(f"migrating {qs.count()} published runs...")
    rows = qs.update(
        workspace_id=Workspace.objects.filter(
            is_personal=True,
            created_by_id=OuterRef("created_by_id"),
        ).values("id")[:1]
    )
    print(f"updated {rows} published runs")
