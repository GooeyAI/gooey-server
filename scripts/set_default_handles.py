from loguru import logger

from app_users.models import AppUser
from handles.models import Handle


def run():
    registered_users = AppUser.objects.filter(
        handle__isnull=True,
        is_anonymous=False,
    )

    for user in registered_users:
        if handle := Handle.create_default_for_user(user):
            user.handle = handle
            user.save()
        else:
            # for-else runs when "break" is not hit in the loop
            logger.warning(f"unable to find acceptable handle for user: {user}")
