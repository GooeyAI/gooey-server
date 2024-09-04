from django.db import IntegrityError, connection
from loguru import logger

from app_users.models import AppUser
from workspaces.models import Workspace


def run():
    migrate_personal_workspaces()
    migrate_txns()


def migrate_personal_workspaces():
    users_without_personal_workspace = AppUser.objects.exclude(
        id__in=Workspace.objects.filter(is_personal=True).values_list(
            "created_by", flat=True
        )
    )

    done_count = 0

    logger.info("Creating personal workspaces...")
    for appuser in users_without_personal_workspace:
        try:
            Workspace.objects.migrate_from_appuser(appuser)
        except IntegrityError as e:
            logger.warning(f"IntegrityError: {e}")
        else:
            done_count += 1

        if done_count % 100 == 0:
            logger.info(f"Running... {done_count} migrated")

    logger.info(f"Migrated {done_count} personal workspaces...")


def migrate_txns():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE app_users_appusertransaction AS txn
            SET workspace_id = workspaces_workspace.id
            FROM
                app_users_appuser
                INNER JOIN workspaces_workspace ON app_users_appuser.id = workspaces_workspace.created_by_id
            WHERE
                txn.user_id = app_users_appuser.id
                AND txn.workspace_id IS NULL
                AND workspaces_workspace.is_personal = true
        """
        )
    logger.info(f"Updated {cursor.rowcount} txns with personal workspaces")
