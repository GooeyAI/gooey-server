from django.core.exceptions import ValidationError
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from loguru import logger
from safedelete.signals import post_softdelete

from app_users.models import AppUser
from workspaces.tasks import send_added_to_workspace_email
from .models import Workspace, WorkspaceInvite, WorkspaceMembership, WorkspaceRole


@receiver(pre_save, sender=AppUser)
def invite_user_to_workspaces_with_matching_domain(instance: AppUser, **kwargs):
    if instance.id or not instance.email:
        # don't send invitation if: 1. user is being updated, 2. user doesn't have an email
        return

    email_domain = instance.email.split("@")[-1].lower()
    for workspace in Workspace.objects.filter(domain_name=email_domain):
        WorkspaceInvite.objects.get_or_create(
            workspace=workspace,
            email=instance.email,
            defaults={"created_by": workspace.created_by},
        )


@receiver(post_save, sender=AppUser)
def auto_accept_invitations_for_user(instance: AppUser, **kwargs):
    if not instance.email:
        return

    for invite in WorkspaceInvite.objects.filter(
        email=instance.email, status=WorkspaceInvite.Status.PENDING
    ):
        try:
            invite.accept(instance, updated_by=instance, auto_accepted=True)
        except ValidationError as e:
            logger.error(
                f"Failed to auto-accept invitation {invite} for user {instance}: {e}"
            )
        else:
            send_added_to_workspace_email.delay(
                invite_id=invite.id, user_id=instance.id
            )


@receiver(post_softdelete, sender=WorkspaceMembership)
def delete_workspace_if_no_members_left(instance: WorkspaceMembership, **kwargs):
    if instance.workspace.memberships.exists():
        return
    logger.info(
        f"Deleting workspace {instance.workspace} because it has no members left"
    )
    instance.workspace.delete()
