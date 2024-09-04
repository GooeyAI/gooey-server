from django.db.models.signals import post_save
from django.dispatch import receiver
from loguru import logger
from safedelete.signals import post_softdelete

from app_users.models import AppUser
from .models import Workspace, WorkspaceMembership, WorkspaceRole


@receiver(post_save, sender=AppUser)
def add_user_existing_workspace(instance: AppUser, **kwargs):
    """
    if the domain name matches
    """
    if not instance.email:
        return

    email_domain = instance.email.split("@")[1]
    workspace = Workspace.objects.filter(domain_name=email_domain).first()
    if not workspace:
        return

    if instance.received_invitations.exists():
        # user has some existing invitations
        return

    workspace_owner = workspace.memberships.filter(role=WorkspaceRole.OWNER).first()
    if not workspace_owner:
        logger.warning(
            f"Workspace {workspace} has no owner. Skipping auto-accept for user {instance}"
        )
        return

    workspace.invite_user(
        invitee_email=instance.email,
        inviter=workspace_owner.user,
        role=WorkspaceRole.MEMBER,
        auto_accept=not instance.workspace_memberships.exists(),  # auto-accept only if user has no existing memberships
    )


@receiver(post_softdelete, sender=WorkspaceMembership)
def delete_workspace_if_no_members_left(instance: WorkspaceMembership, **kwargs):
    if instance.workspace.memberships.exists():
        return

    logger.info(
        f"Deleting workspace {instance.workspace} because it has no members left"
    )
    instance.workspace.delete()
