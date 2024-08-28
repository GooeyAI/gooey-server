from django.db import IntegrityError
from loguru import logger

from app_users.models import AppUser
from orgs.models import Org


def run():
    users_without_personal_org = AppUser.objects.exclude(
        id__in=Org.objects.filter(is_personal=True).values_list("created_by", flat=True)
    )

    done_count = 0

    for appuser in users_without_personal_org:
        try:
            Org.objects.migrate_from_appuser(appuser)
        except IntegrityError as e:
            logger.warning(f"IntegrityError: {e}")
        else:
            done_count += 1

        if done_count % 100 == 0:
            logger.info(f"Running... {done_count} migrated")

    logger.info(f"Done... {done_count} migrated")
