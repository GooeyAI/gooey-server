from django.dispatch import receiver
from loguru import logger
from safedelete.signals import post_softdelete

from .models import WorkspaceMembership


@receiver(post_softdelete, sender=WorkspaceMembership)
def delete_workspace_if_no_members_left(instance: WorkspaceMembership, **kwargs):
    if instance.workspace.memberships.exists():
        return
    logger.info(
        f"Deleting workspace {instance.workspace} because it has no members left"
    )
    instance.workspace.delete()
