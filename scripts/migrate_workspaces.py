from time import sleep

from django.db import transaction
from django.db.models import OuterRef, Subquery

from app_users.models import AppUser, AppUserTransaction
from bots.models import SavedRun, PublishedRun
from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole

BATCH_SIZE = 10_000
DELAY = 0.1
SEP = " ... "


def run():
    migrate_personal_workspaces()
    migrate_txns()
    migrate_saved_runs()
    ## LATER
    # migrate_published_runs()


@transaction.atomic
def migrate_personal_workspaces():
    users = AppUser.objects.exclude(created_workspaces__is_personal=True)

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
    print(f"creating {len(workspaces)} workspaces ...")
    workspaces = Workspace.objects.bulk_create(workspaces)

    memberships = [
        WorkspaceMembership(
            workspace=workspace,
            user=user,
            role=WorkspaceRole.OWNER,
        )
        for user, workspace in zip(users, workspaces)
        if workspace.id
    ]
    print(f"creating {len(memberships)} memberships ...")
    WorkspaceMembership.objects.bulk_create(memberships)


def migrate_txns():
    qs = AppUserTransaction.objects.filter(workspace__isnull=True)
    print(f"migrating {qs.count()} txns", end=SEP)
    update_in_batches(
        qs,
        workspace_id=Workspace.objects.filter(
            is_personal=True, created_by=OuterRef("user")
        ).values("id")[:1],
    )


def migrate_saved_runs():
    qs = SavedRun.objects.filter(workspace__isnull=True, uid__isnull=False).exclude(
        uid=""
    )
    print(f"migrating {qs.count()} saved runs", end=SEP)
    update_in_batches(
        qs,
        workspace_id=Workspace.objects.filter(
            is_personal=True,
            created_by__uid=OuterRef("uid"),
        ).values("id")[:1],
    )


def migrate_published_runs():
    qs = PublishedRun.objects.filter(workspace__isnull=True, created_by__isnull=False)
    print(f"migrating {qs.count()} published runs", end=SEP)
    update_in_batches(
        qs,
        workspace_id=Subquery(
            Workspace.objects.filter(
                is_personal=True,
                created_by_id=OuterRef("created_by_id"),
            ).values("id")[:1]
        ),
    )


def update_in_batches(qs, **kwargs):
    total = 0
    while True:
        rows = qs.model.objects.filter(id__in=qs[:BATCH_SIZE]).update(**kwargs)
        sleep(DELAY)  # let the db breathe
        if not rows:
            print("Done!")
            break
        total += rows
        print(total, end=SEP)
