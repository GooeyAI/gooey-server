import traceback

import sentry_sdk
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from loguru import logger
from safedelete.signals import post_softdelete

from app_users.models import AppUser
from .models import Workspace, WorkspaceInvite, WorkspaceMembership, WorkspaceRole


@receiver(post_save, sender=AppUser)
def add_user_existing_workspace(instance: AppUser, **kwargs):
    """
    if the domain name matches, add the user to the workspace
    """
    if not instance.email:
        return

    email_domain = instance.email.split("@")[-1].lower()
    for workspace in Workspace.objects.filter(domain_name=email_domain):
        try:
            WorkspaceInvite.objects.create_and_send_invite(
                workspace=workspace,
                email=instance.email,
                current_user=workspace.created_by,
                defaults=dict(role=WorkspaceRole.MEMBER),
            )
        except ValidationError as e:
            traceback.print_exc()
            sentry_sdk.capture_exception(e)

    for invite in WorkspaceInvite.objects.filter(email__iexact=instance.email):
        try:
            invite.accept(instance, auto_accepted=True)
        except ValidationError:
            traceback.print_exc()


@receiver(post_softdelete, sender=WorkspaceMembership)
def delete_workspace_if_no_members_left(instance: WorkspaceMembership, **kwargs):
    if instance.workspace.memberships.exists():
        return
    logger.info(
        f"Deleting workspace {instance.workspace} because it has no members left"
    )
    instance.workspace.delete()


@receiver(pre_save, sender=Workspace)
def add_members_on_workspace_domain_change(instance: Workspace, **kwargs):
    if instance.id:
        old_workspace_domain = (
            Workspace.objects.filter(id=instance.id)
            .values_list("domain_name", flat=True)
            .first()
        )
    else:
        old_workspace_domain = None
    if instance.domain_name and instance.domain_name != old_workspace_domain:
        transaction.on_commit(instance.add_domain_members)
