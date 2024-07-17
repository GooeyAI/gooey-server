import sys

from django.core import serializers
from django.db.models import NOT_PROVIDED

from app_users.models import AppUser
from bots.models import BotIntegration, PublishedRun, PublishedRunVisibility

USER_FIELDS = {
    "id",
    "is_anonymous",
    "uid",
    "display_name",
    "balance",
}


def run(*args):
    with open("fixture.json", "w") as f:
        objs = {
            f"{type(obj)}:{obj.pk}": obj for obj in filter(None, get_objects(*args))
        }.values()
        print(f"Exporting {len(objs)} objects")
        serializers.serialize(
            "json",
            objs,
            indent=2,
            stream=f,
            progress_output=sys.stdout,
            object_count=len(objs),
        )


def get_objects(*args):
    for pr in PublishedRun.objects.filter(
        is_approved_example=True,
        visibility=PublishedRunVisibility.PUBLIC,
    ):
        if pr.saved_run_id:
            yield export(pr.saved_run)
        if pr.created_by_id:
            yield pr.created_by.handle
            yield export(pr.created_by, only_include=USER_FIELDS)
        if pr.last_edited_by_id:
            yield pr.last_edited_by.handle
            yield export(pr.last_edited_by, only_include=USER_FIELDS)
        yield export(pr, include_fks={"saved_run", "created_by", "last_edited_by"})

        for version in pr.versions.all():
            yield export(version.saved_run)
            yield export(version, include_fks={"saved_run", "published_run"})

    if "bots" not in args:
        return
    for obj in BotIntegration.objects.all():
        user = AppUser.objects.get(uid=obj.billing_account_uid)
        yield user.handle
        yield export(user, only_include=USER_FIELDS)

        if obj.saved_run_id:
            yield export(obj.saved_run)

        if obj.published_run_id:
            yield export(obj.published_run.saved_run)
            yield export(obj.published_run, include_fks={"saved_run"})

        yield export(obj, include_fks={"saved_run", "published_run"})


def export(obj, *, include_fks=(), only_include=None):
    for field in obj._meta.get_fields():
        if field.is_relation and field.name not in include_fks:
            try:
                setattr(obj, field.name, None)
            except TypeError:
                pass
        elif only_include and field.name not in only_include:
            if field.default == NOT_PROVIDED:
                default = None
            else:
                default = field.default
            try:
                default = default()
            except TypeError:
                pass
            setattr(obj, field.name, default)
    return obj
