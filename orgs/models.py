import re
from datetime import timedelta

from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.db.backends.base.schema import logger
from django.db.models.query_utils import Q
from django.utils import timezone
from django.utils.text import slugify
from safedelete.managers import SafeDeleteManager
from safedelete.models import SafeDeleteModel, SOFT_DELETE_CASCADE

from app_users.models import AppUser
from daras_ai_v2 import settings
from daras_ai_v2.fastapi_tricks import get_route_url
from daras_ai_v2.crypto import get_random_doc_id
from orgs.tasks import send_auto_accepted_email, send_invitation_email


ORG_DOMAIN_NAME_RE = re.compile(r"^[a-z0-9]+([\-\.]{1}[a-z0-9]+)*\.[a-z]+$")


def validate_org_domain_name(value):
    from handles.models import COMMON_EMAIL_DOMAINS

    if not ORG_DOMAIN_NAME_RE.fullmatch(value):
        raise ValidationError("Invalid domain name")

    if value in COMMON_EMAIL_DOMAINS:
        raise ValidationError("This domain name is reserved")


class OrgRole(models.IntegerChoices):
    OWNER = 1
    ADMIN = 2
    MEMBER = 3


class OrgManager(SafeDeleteManager):
    def create_org(self, *, created_by: "AppUser", org_id: str | None = None, **kwargs):
        org = self.model(
            org_id=org_id or get_random_doc_id(), created_by=created_by, **kwargs
        )
        org.full_clean()
        org.save()
        org.add_member(
            created_by,
            role=OrgRole.OWNER,
        )
        return org


class Org(SafeDeleteModel):
    _safedelete_policy = SOFT_DELETE_CASCADE

    org_id = models.CharField(max_length=100, null=True, blank=True, unique=True)

    name = models.CharField(max_length=100)
    created_by = models.ForeignKey(
        "app_users.appuser",
        on_delete=models.CASCADE,
    )

    logo = models.URLField(null=True, blank=True)
    domain_name = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        validators=[
            validate_org_domain_name,
        ],
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OrgManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["domain_name"],
                condition=Q(deleted__isnull=True),
                name="unique_domain_name_when_not_deleted",
                violation_error_message=f"This domain name is already in use by another team. Contact {settings.SUPPORT_EMAIL} if you think this is a mistake.",
            )
        ]

    def __str__(self):
        if self.deleted:
            return f"[Deleted] {self.name}"
        else:
            return self.name

    def get_slug(self):
        return slugify(self.name)

    def add_member(
        self, user: AppUser, role: OrgRole, invitation: "OrgInvitation | None" = None
    ):
        OrgMembership(
            org=self,
            user=user,
            role=role,
            invitation=invitation,
        ).save()

    def invite_user(
        self,
        *,
        invitee_email: str,
        inviter: AppUser,
        role: OrgRole,
        auto_accept: bool = False,
    ) -> "OrgInvitation":
        """
        auto_accept: If True, the user will be automatically added if they have an account
        """
        for member in self.memberships.all().select_related("user"):
            if member.user.email == invitee_email:
                raise ValidationError(f"{member.user} is already a member of this team")

        for invitation in self.invitations.filter(status=OrgInvitation.Status.PENDING):
            if invitation.invitee_email == invitee_email:
                raise ValidationError(
                    f"{invitee_email} was already invited to this team"
                )

        invitation = OrgInvitation(
            invite_id=get_random_doc_id(),
            org=self,
            invitee_email=invitee_email,
            inviter=inviter,
            role=role,
        )
        invitation.full_clean()
        invitation.save()

        if auto_accept:
            try:
                invitation.auto_accept()
            except AppUser.DoesNotExist:
                pass

        if not invitation.auto_accepted:
            invitation.send_email()

        return invitation


class OrgMembership(SafeDeleteModel):
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        "app_users.AppUser", on_delete=models.CASCADE, related_name="org_memberships"
    )
    invitation = models.OneToOneField(
        "OrgInvitation",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        default=None,
        related_name="membership",
    )

    role = models.IntegerField(choices=OrgRole.choices, default=OrgRole.MEMBER)

    created_at = models.DateTimeField(auto_now_add=True)  # same as joining date
    updated_at = models.DateTimeField(auto_now=True)

    objects = SafeDeleteManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org", "user"],
                condition=Q(deleted__isnull=True),
                name="unique_org_user",
            )
        ]

    def __str__(self):
        return f"{self.get_role_display()} - {self.user} ({self.org})"

    def can_edit_org_metadata(self):
        return self.role in (OrgRole.OWNER, OrgRole.ADMIN)

    def can_delete_org(self):
        return self.role == OrgRole.OWNER

    def has_higher_role_than(self, other: "OrgMembership"):
        # creator > owner > admin > member
        match other.role:
            case OrgRole.OWNER:
                return self.org.created_by == OrgRole.OWNER
            case OrgRole.ADMIN:
                return self.role == OrgRole.OWNER
            case OrgRole.MEMBER:
                return self.role in (OrgRole.OWNER, OrgRole.ADMIN)

    def can_change_role(self, other: "OrgMembership"):
        return self.has_higher_role_than(other)

    def can_kick(self, other: "OrgMembership"):
        return self.has_higher_role_than(other)

    def can_transfer_ownership(self):
        return self.role == OrgRole.OWNER

    def can_invite(self):
        return self.role in (OrgRole.OWNER, OrgRole.ADMIN)


class OrgInvitation(SafeDeleteModel):
    class Status(models.IntegerChoices):
        PENDING = 1
        ACCEPTED = 2
        REJECTED = 3
        CANCELED = 4
        EXPIRED = 5

    invite_id = models.CharField(max_length=100, unique=True)
    invitee_email = models.EmailField()

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="invitations")
    inviter = models.ForeignKey(
        "app_users.AppUser", on_delete=models.CASCADE, related_name="sent_invitations"
    )

    status = models.IntegerField(choices=Status.choices, default=Status.PENDING)
    auto_accepted = models.BooleanField(default=False)
    role = models.IntegerField(choices=OrgRole.choices, default=OrgRole.MEMBER)

    last_email_sent_at = models.DateTimeField(null=True, blank=True, default=None)
    status_changed_at = models.DateTimeField(null=True, blank=True, default=None)
    status_changed_by = models.ForeignKey(
        "app_users.AppUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_invitations",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.invitee_email} - {self.org} ({self.get_status_display()})"

    def has_expired(self):
        return self.status == self.Status.EXPIRED or (
            timezone.now() - (self.last_email_sent_at or self.created_at)
            > timedelta(days=settings.ORG_INVITATION_EXPIRY_DAYS)
        )

    def auto_accept(self):
        """
        Automatically accept the invitation if user has an account.

        If user is already part of the team, then the invitation will be canceled.

        Raises: ValidationError
        """
        assert self.status == self.Status.PENDING

        invitee = AppUser.objects.get(email=self.invitee_email)
        self.accept(invitee, auto_accepted=True)

        if self.auto_accepted:
            logger.info(f"User {invitee} auto-accepted invitation to org {self.org}")
            send_auto_accepted_email.delay(self.pk)

    def get_url(self):
        from routers.account import invitation_route

        return get_route_url(
            invitation_route,
            params={"invite_id": self.invite_id, "org_slug": self.org.get_slug()},
        )

    def send_email(self):
        # pre-emptively set last_email_sent_at to avoid sending multiple emails concurrently
        if not self.can_resend_email():
            raise ValidationError("This user has already been invited recently.")

        self.last_email_sent_at = timezone.now()
        self.save(update_fields=["last_email_sent_at"])

        send_invitation_email.delay(invitation_pk=self.pk)

    def accept(self, user: AppUser, *, auto_accepted: bool = False):
        """
        Raises: ValidationError
        """
        # can't accept an invitation that is already accepted / rejected / canceled
        if self.status != self.Status.PENDING:
            raise ValidationError(
                f"This invitation has been {self.get_status_display().lower()}."
            )

        if self.has_expired():
            self.status = self.Status.EXPIRED
            self.save()
            raise ValidationError(
                "This invitation has expired. Please ask your team admin to send a new one."
            )

        if self.org.memberships.filter(user_id=user.pk).exists():
            raise ValidationError(f"User is already a member of this team.")

        self.status = self.Status.ACCEPTED
        self.auto_accepted = auto_accepted
        self.status_changed_at = timezone.now()
        self.status_changed_by = user

        self.full_clean()

        with transaction.atomic():
            user.org_memberships.all().delete()  # delete current memberships
            self.org.add_member(
                user,
                role=self.role,
                invitation=self,
            )
            self.save()

    def reject(self, user: AppUser):
        self.status = self.Status.REJECTED
        self.status_changed_at = timezone.now()
        self.status_changed_by = user
        self.save()

    def cancel(self, user: AppUser):
        self.status = self.Status.CANCELED
        self.status_changed_at = timezone.now()
        self.status_changed_by = user
        self.save()

    def can_resend_email(self):
        if not self.last_email_sent_at:
            return True

        return timezone.now() - self.last_email_sent_at > timedelta(
            seconds=settings.ORG_INVITATION_EMAIL_COOLDOWN_INTERVAL
        )
