from django.db.models.signals import post_save
from django.dispatch import receiver
from loguru import logger
from safedelete.signals import post_softdelete

from app_users.models import AppUser
from orgs.models import Org, OrgMembership, OrgRole
from orgs.tasks import send_auto_accepted_email


@receiver(post_save, sender=AppUser)
def add_user_existing_org(instance: AppUser, **kwargs):
    """
    if the domain name matches
    """
    if not instance.email:
        return

    email_domain = instance.email.split("@")[1]
    org = Org.objects.filter(domain_name=email_domain).first()
    if not org:
        return

    if instance.received_invitations.exists():
        # user has some existing invitations
        return

    org_owner = org.memberships.filter(role=OrgRole.OWNER).first()
    if not org_owner:
        logger.warning(
            f"Org {org} has no owner. Skipping auto-accept for user {instance}"
        )
        return

    invitation = org.invite_user(
        invitee_email=instance.email,
        inviter=org_owner.user,
        role=OrgRole.MEMBER,
        auto_accept=not instance.org_memberships.exists(),  # auto-accept only if user has no existing memberships
    )


@receiver(post_softdelete, sender=OrgMembership)
def delete_org_if_no_members_left(instance: OrgMembership, **kwargs):
    if instance.org.memberships.exists():
        return

    logger.info(f"Deleting org {instance.org} because it has no members left")
    instance.org.delete()
