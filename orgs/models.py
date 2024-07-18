import re

from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.utils.text import slugify
from safedelete.managers import SafeDeleteManager
from safedelete.models import SafeDeleteModel, SOFT_DELETE_CASCADE

from app_users.models import AppUser
from daras_ai_v2.crypto import get_random_doc_id


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
        org.members.add(
            created_by,
            through_defaults={
                "role": OrgRole.OWNER,
            },
        )
        return org


class Org(SafeDeleteModel):
    _safedelete_policy = SOFT_DELETE_CASCADE

    org_id = models.CharField(max_length=100, null=True, blank=True, unique=True)

    name = models.CharField(max_length=100)
    members = models.ManyToManyField(
        "app_users.AppUser",
        through="OrgMembership",
        related_name="orgs",
    )
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
        unique_together = ("domain_name", "deleted")

    def __str__(self):
        if self.deleted:
            return f"[Deleted] {self.name}"
        else:
            return self.name

    def get_slug(self):
        return slugify(self.name)

    def invite_user(
        self,
        *,
        invitee_email: str,
        inviter: AppUser,
        role: OrgRole,
        auto_accept: bool = True,
    ):
        """
        auto_accept: If True, the user will be automatically added if they have an account
        """
        for member in self.members.all():
            if member.email == invitee_email:
                raise ValidationError(f"{member} is already a member of this team")

        for invitation in self.invitations.filter(status=OrgInvitation.Status.PENDING):
            if invitation.invitee_email == invitee_email:
                raise ValidationError(
                    f"{invitee_email} was already invited to this team"
                )

        invitation = OrgInvitation(
            org=self,
            invitee_email=invitee_email,
            inviter=inviter,
            role=role,
        )
        invitation.full_clean()
        invitation.save()

        if auto_accept:
            try:
                invitation.accept(auto_accepted=True)
            except AppUser.DoesNotExist:
                pass


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

    class Meta:
        unique_together = ("org", "user", "deleted")

    def __str__(self):
        return f"{self.get_role_display()} - {self.user} ({self.org})"

    def can_edit_org_metadata(self):
        return self.role in (OrgRole.OWNER, OrgRole.ADMIN)

    def can_delete_org(self):
        return self.role == OrgRole.OWNER

    def can_invite(self):
        return self.role in (OrgRole.OWNER, OrgRole.ADMIN)

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


class OrgInvitation(SafeDeleteModel):
    class Status(models.IntegerChoices):
        PENDING = 1
        ACCEPTED = 2
        REJECTED = 3
        CANCELED = 4

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="invitations")
    invitee_email = models.EmailField()
    inviter = models.ForeignKey("app_users.AppUser", on_delete=models.CASCADE)

    status = models.IntegerField(choices=Status.choices, default=Status.PENDING)
    auto_accepted = models.BooleanField(default=False)
    role = models.IntegerField(choices=OrgRole.choices, default=OrgRole.MEMBER)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.invitee_email} - {self.org} ({self.get_status_display()})"

    def accept(self, *, auto_accepted: bool = False):
        assert self.status == self.Status.PENDING

        invitee = AppUser.objects.get(email=self.invitee_email)

        self.status = self.Status.ACCEPTED
        self.auto_accepted = auto_accepted

        with transaction.atomic():
            self.org.members.add(
                invitee,
                through_defaults={
                    "role": self.role,
                    "invitation": self,
                },
            )
            self.save()

    def reject(self):
        self.status = self.Status.REJECTED
        self.save()

    def cancel(self):
        self.status = self.Status.CANCELED
        self.save()