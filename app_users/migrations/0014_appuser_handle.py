import re
import uuid

import django.db.models.deletion
from django.core.exceptions import ValidationError
from django.db import IntegrityError, migrations, models

from loguru import logger

from app_users.models import AppUser
from handles.models import HANDLE_ALLOWED_CHARS, HANDLE_MAX_LENGTH


def create_default_handle_for_user(Handle, user):
    for handle_name in _generate_handle_options(user):
        if handle := _attempt_create_handle(Handle, handle_name):
            return handle
    return None


def _make_handle_from(name):
    name = name.lower()
    name = "-".join(
        re.findall(HANDLE_ALLOWED_CHARS, name)
    )  # find groups of valid chars
    name = re.sub(r"-+", "-", name)  # remove consecutive dashes
    name = name[:HANDLE_MAX_LENGTH]
    name = name.rstrip("-_")
    return name


def _generate_handle_options(user):
    first_name_handle = _make_handle_from(AppUser.first_name(user))
    if first_name_handle:
        yield first_name_handle

    email_handle = _make_handle_from(user.email.split("@")[0]) if user.email else ""
    if email_handle:
        yield email_handle

    if first_name_handle:
        yield first_name_handle + f"-{str(user.pk)[:2]}"
        yield first_name_handle + f"-{uuid.uuid4().hex[:4]}"

    if email_handle:
        yield email_handle + f"-{str(user.pk)[:2]}"
        yield email_handle + f"-{uuid.uuid4().hex[:4]}"

    for _ in range(5):
        # generate random handles
        yield f"user-{uuid.uuid4().hex[:8]}"


def _attempt_create_handle(Handle, handle_name):
    handle = Handle(name=handle_name)
    try:
        handle.full_clean()
        handle.save()
        return handle
    except (IntegrityError, ValidationError):
        return None


def forwards_func(apps, schema_editor):
    AppUser = apps.get_model("app_users", "AppUser")
    Handle = apps.get_model("handles", "Handle")

    registered_users = AppUser.objects.filter(
        handle__isnull=True,
        is_anonymous=False,
        email__isnull=False,
    )

    for user in registered_users:
        if handle := create_default_handle_for_user(Handle, user):
            user.handle = handle
            user.save()
        else:
            # for-else runs when "break" is not hit in the loop
            logger.warning(f"unable to find acceptable handle for user: {user}")


class Migration(migrations.Migration):

    dependencies = [
        ("handles", "0001_initial"),
        (
            "app_users",
            "0013_appusertransaction_app_users_a_user_id_9b2e8d_idx_and_more",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="appuser",
            name="handle",
            field=models.OneToOneField(
                blank=True,
                default=None,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="user",
                to="handles.handle",
            ),
        ),
        migrations.RunPython(forwards_func, reverse_code=migrations.RunPython.noop),
    ]
