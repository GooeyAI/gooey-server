from django.db import IntegrityError, connection
from loguru import logger

from app_users.models import AppUser
from orgs.models import Org


def run():
    migrate_personal_orgs()
    migrate_txns()


def migrate_personal_orgs():
    users_without_personal_org = AppUser.objects.exclude(
        id__in=Org.objects.filter(is_personal=True).values_list("created_by", flat=True)
    )

    done_count = 0

    logger.info("Creating personal orgs...")
    for appuser in users_without_personal_org:
        try:
            Org.objects.migrate_from_appuser(appuser)
        except IntegrityError as e:
            logger.warning(f"IntegrityError: {e}")
        else:
            done_count += 1

        if done_count % 100 == 0:
            logger.info(f"Running... {done_count} migrated")

    logger.info(f"Migrated {done_count} personal orgs...")


def migrate_txns():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE app_users_appusertransaction AS txn
            SET org_id = orgs_org.id
            FROM
                app_users_appuser
                INNER JOIN orgs_org ON app_users_appuser.id = orgs_org.created_by_id
            WHERE
                txn.user_id = app_users_appuser.id
                AND txn.org_id IS NULL
                AND orgs_org.is_personal = true
        """
        )
    logger.info(f"Updated {cursor.rowcount} txns with personal orgs")
