from contextlib import contextmanager
from itertools import islice
from time import sleep

from django.db import transaction
from django.db.models import OuterRef, Subquery

from api_keys.models import ApiKey
from app_users.models import AppUser, AppUserTransaction
from bots.models import SavedRun, PublishedRun
from daras_ai_v2 import db
from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole

BATCH_SIZE = 10_000
FIREBASE_BATCH_SIZE = 100
DELAY = 0.1
SEP = " ... "


def run():
    migrate_personal_workspaces()
    migrate_txns()
    migrate_saved_runs()
    migrate_published_runs()
    migrate_api_keys()


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


def migrate_api_keys():
    firebase_stream = db.get_client().collection(db.API_KEYS_COLLECTION).stream()

    total = 0
    while True:
        batch = list(islice(firebase_stream, FIREBASE_BATCH_SIZE))
        if not batch:
            print("Done!")
            break
        cached_workspaces = Workspace.objects.select_related("created_by").filter(
            is_personal=True,
            created_by__uid__in=[snap.get("uid") for snap in batch],
        )
        cached_workspaces_by_uid = {w.created_by.uid: w for w in cached_workspaces}

        with (
            disable_auto_now_add(ApiKey, "created_at"),
            disable_auto_now(ApiKey, "updated_at"),
        ):
            migrated_keys = ApiKey.objects.bulk_create(
                [
                    ApiKey(
                        hash=snap.get("secret_key_hash"),
                        preview=snap.get("secret_key_preview"),
                        workspace_id=cached_workspaces_by_uid[snap.get("uid")].id,
                        created_by_id=cached_workspaces_by_uid[
                            snap.get("uid")
                        ].created_by.id,
                        created_at=snap.get("created_at"),
                        updated_at=snap.get("created_at"),
                    )
                    for snap in batch
                    if snap.get("uid") in cached_workspaces_by_uid
                ],
                ignore_conflicts=True,
                unique_fields=("hash",),
            )
            print(total, f"({len(migrated_keys)}/{len(batch)})", end=SEP)
            total += len(migrated_keys)


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


@contextmanager
def disable_auto_now(model, field_name):
    for field in model._meta.local_fields:
        if field.name == field_name:
            field.auto_now = False
            yield
            field.auto_now = True
            break


@contextmanager
def disable_auto_now_add(model, field_name):
    for field in model._meta.local_fields:
        if field.name == field_name:
            field.auto_now_add = False
            yield
            field.auto_now_add = True
            break
