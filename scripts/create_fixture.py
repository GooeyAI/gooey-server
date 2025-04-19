import sys

from django.core import serializers
from django.db.models import NOT_PROVIDED

from app_users.models import AppUser
from bots.models import (
    BotIntegration,
    PublishedRun,
    WorkflowAccessLevel,
)
from daras_ai_v2 import settings
from workspaces.models import Workspace


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
    # export all root recipes and 100 latest examples
    pr_qs = (
        list(
            PublishedRun.objects.filter(published_run_id=""),
        )
        + list(
            PublishedRun.objects.filter(
                PublishedRun.approved_example_q(),
            ).order_by("-updated_at")[:200],
        )
        + list(
            PublishedRun.objects.filter(
                published_run_id__in=[
                    settings.SAFETY_CHECKER_EXAMPLE_ID,
                    settings.INTEGRATION_DETAILS_GENERATOR_EXAMPLE_ID,
                ]
            )
        )
    )
    for pr in pr_qs:
        yield from export_pr(pr)

    # export all public bots
    bots_qs = BotIntegration.objects.filter(
        published_run__is_approved_example=True,
    ).exclude(
        published_run__public_access=WorkflowAccessLevel.VIEW_ONLY,
    )
    for bi in bots_qs:
        if bi.workspace_id:
            yield from export_workspace(bi.workspace)
        if bi.created_by_id:
            yield from export_user(bi.created_by)
        if bi.saved_run_id:
            yield export(bi.saved_run)
        if bi.published_run_id:
            yield from export_pr(bi.published_run)
        yield export(
            bi,
            include_fks={"workspace", "created_by", "saved_run", "published_run"},
            # exclude sensitive fields from the export
            exclude={
                "fb_page_access_token",
                "wa_phone_number_id",
                "wa_business_access_token",
                "wa_business_waba_id",
                "wa_business_user_id",
                "wa_business_name",
                "wa_business_account_name",
                "slack_channel_hook_url",
                "slack_access_token",
                "twilio_phone_number_sid",
                "twilio_account_sid",
                "twilio_username",
                "twilio_password",
            },
        )

    user_qs = AppUser.objects.filter(email=settings.SAFETY_CHECKER_BILLING_EMAIL)
    for user in user_qs:
        yield from export_user(user)


def export_pr(pr: PublishedRun):
    if pr.workspace_id:
        yield from export_workspace(pr.workspace)
    if pr.created_by_id:
        yield from export_user(pr.created_by)
    if pr.last_edited_by_id:
        yield from export_user(pr.last_edited_by)
    if pr.saved_run_id:
        yield export(pr.saved_run)
    yield export(
        pr,
        include_fks={"workspace", "created_by", "last_edited_by", "saved_run"},
    )
    for version in pr.versions.all():
        yield export(version.saved_run)
        yield export(version, include_fks={"saved_run", "published_run"})


def export_workspace(workspace: Workspace):
    yield from export_user(workspace.created_by)
    if workspace.handle_id:
        yield export(workspace.handle)
    yield export(workspace, include_fks={"created_by", "handle"})


def export_user(user: AppUser):
    yield export(
        user,
        only_include={
            "id",
            "is_anonymous",
            "uid",
            "display_name",
            "balance",
            "created_at",
            "updated_at",
        },
    )


def export(obj, *, include_fks=(), only_include=None, exclude=None):
    for field in obj._meta.get_fields():
        if field.is_relation and field.name not in include_fks:
            try:
                setattr(obj, field.name, None)
            except TypeError:
                pass
        elif (only_include and field.name not in only_include) or (
            exclude and field.name in exclude
        ):
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
