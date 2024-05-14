import sys

from django.core import serializers

from app_users.models import AppUser
from bots.models import BotIntegration, PublishedRun, PublishedRunVisibility


def run():
    with open("fixture.json", "w") as f:
        objs = list(filter(None, get_objects()))
        print(f"Exporting {len(objs)} objects")
        serializers.serialize(
            "json",
            objs,
            indent=2,
            stream=f,
            progress_output=sys.stdout,
            object_count=len(objs),
        )


def get_objects():
    for pr in PublishedRun.objects.filter(
        is_approved_example=True,
        visibility=PublishedRunVisibility.PUBLIC,
    ):
        if pr.saved_run_id:
            yield export(pr.saved_run)
        if pr.created_by_id:
            yield export(pr.created_by)
        if pr.last_edited_by_id:
            yield export(pr.last_edited_by)
        yield export(pr, ["saved_run", "created_by", "last_edited_by"])

        for version in pr.versions.all():
            yield export(version.saved_run)
            yield export(version, ["published_run", "saved_run"])

    for obj in BotIntegration.objects.all():
        user = AppUser.objects.get(uid=obj.billing_account_uid)
        yield user.handle
        yield user

        if obj.saved_run_id:
            yield export(obj.saved_run)

        if obj.published_run_id:
            yield export(obj.published_run.saved_run)
            yield export(obj.published_run, ["saved_run"])

        yield export(obj, ["saved_run", "published_run"])


def export(obj, exclude=()):
    for field in obj._meta.get_fields():
        if field.name in exclude:
            continue
        if field.is_relation:
            try:
                setattr(obj, field.name, None)
            except TypeError:
                pass
    return obj
