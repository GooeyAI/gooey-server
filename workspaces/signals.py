from django.db.models.signals import post_save
from django.dispatch import receiver
from loguru import logger
from safedelete.signals import post_softdelete

from app_users.models import AppUser
from .models import Workspace, WorkspaceMembership
from .tasks import send_added_to_workspace_email


@receiver(post_save, sender=AppUser)
def add_user_existing_workspace(instance: AppUser, **kwargs):
    """
    if the domain name matches
    """
    if not instance.email:
        return
    email_domain = instance.email.split("@")[1].lower()
    for workspace in Workspace.objects.filter(domain_name=email_domain):
        WorkspaceMembership.objects.get_or_create(workspace=workspace, user=instance)
        send_added_to_workspace_email.delay(
            workspace_id=workspace.id, user_id=instance.id
        )


@receiver(post_softdelete, sender=WorkspaceMembership)
def delete_workspace_if_no_members_left(instance: WorkspaceMembership, **kwargs):
    if instance.workspace.memberships.exists():
        return
    logger.info(
        f"Deleting workspace {instance.workspace} because it has no members left"
    )
    instance.workspace.delete()
