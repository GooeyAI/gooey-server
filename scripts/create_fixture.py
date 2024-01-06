import sys

from django.core import serializers

from app_users.models import AppUser
from bots.models import BotIntegration, PublishedRun


def run():
    with open("fixture.json", "w") as f:
        objs = list(get_objects())
        serializers.serialize(
            "json",
            objs,
            indent=2,
            stream=f,
            progress_output=sys.stdout,
            object_count=len(objs),
        )


def get_objects():
    for pr in PublishedRun.objects.all():
        set_fk_null(pr.saved_run)
        if pr.saved_run_id:
            yield pr.saved_run
        if pr.created_by_id:
            yield pr.created_by
        if pr.last_edited_by_id:
            yield pr.last_edited_by
        yield pr

        for version in pr.versions.all():
            set_fk_null(version.saved_run)
            yield version.saved_run
            if version.changed_by_id:
                yield version.changed_by
            yield version

    for obj in BotIntegration.objects.all():
        if not obj.saved_run_id:
            continue
        set_fk_null(obj.saved_run)
        yield obj.saved_run

        yield AppUser.objects.get(uid=obj.billing_account_uid)
        yield obj


def set_fk_null(obj):
    for field in obj._meta.get_fields():
        if field.is_relation and field.many_to_one:
            setattr(obj, field.name, None)
