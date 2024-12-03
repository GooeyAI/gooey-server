import traceback
from django.db.models.signals import post_save
from django.dispatch import receiver
from loguru import logger
from safedelete.signals import post_softdelete
import sentry_sdk

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
                created_by=workspace.created_by,
                defaults=dict(role=WorkspaceRole.MEMBER),
            )
        except Exception as e:
            traceback.print_exc()
            sentry_sdk.capture_exception(e)


@receiver(post_softdelete, sender=WorkspaceMembership)
def delete_workspace_if_no_members_left(instance: WorkspaceMembership, **kwargs):
    if instance.workspace.memberships.exists():
        return
    logger.info(
        f"Deleting workspace {instance.workspace} because it has no members left"
    )
    instance.workspace.delete()
