from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.text import slugify

from app_users.models import AppUser
from daras_ai_v2.crypto import get_random_doc_id


class OrgRole(models.IntegerChoices):
    OWNER = 1
    ADMIN = 2
    MEMBER = 3


class OrgQuerySet(models.QuerySet):
    def create_org(self, *, created_by: "AppUser", org_id: str | None = None, **kwargs):
        org = self.create(
            org_id=org_id or get_random_doc_id(), created_by=created_by, **kwargs
        )
        org.members.add(
            created_by,
            through_defaults={
                "role": OrgRole.OWNER,
            },
        )
        return org


class OrgManager(models.Manager):
    def get_queryset(self):
        return OrgQuerySet(self.model, using=self._db).filter(deleted_at__isnull=True)


class Org(models.Model):
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

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True, default=None)

    objects = OrgManager()

    def __str__(self):
        return self.name

    def get_slug(self):
        return slugify(self.name)

    def is_deleted(self):
        return self.deleted_at is not None

    def soft_delete(self):
        with transaction.atomic():
            for m in self.memberships.all():
                m.delete()
            self.deleted_at = timezone.now()
            self.save()

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
                raise ValidationError(f"{member} is already a member of this org")

        for invitation in self.invitations.filter(status=OrgInvitation.Status.PENDING):
            if invitation.invitee_email == invitee_email:
                raise ValidationError(f"{invitee_email} was already invited")

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


class OrgMembership(models.Model):
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
        unique_together = ("org", "user")

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

    def can_transfer_ownership(self, other: "OrgMembership"):
        return self.role == OrgRole.OWNER and other.role == OrgRole.ADMIN


class OrgInvitation(models.Model):
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

    # TODO: don't spam invitees!
    # invitation_email_count = models.IntegerField(default=0)
    # last_invitation_sent_at = models.DateTimeField(null=True, blank=True)

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
