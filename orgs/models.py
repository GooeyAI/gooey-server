from __future__ import annotations

import re
from datetime import timedelta

from django.db.models.aggregates import Sum
import stripe
from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.db.backends.base.schema import logger
from django.db.models.query_utils import Q
from django.utils import timezone
from django.utils.text import slugify
from safedelete.managers import SafeDeleteManager
from safedelete.models import SafeDeleteModel, SOFT_DELETE_CASCADE

from daras_ai_v2 import settings
from daras_ai_v2.fastapi_tricks import get_app_route_url
from daras_ai_v2.crypto import get_random_doc_id
from gooeysite.bg_db_conn import db_middleware
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
    def create_org(
        self, *, created_by: "AppUser", org_id: str | None = None, **kwargs
    ) -> Org:
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

    def get_or_create_from_org_id(self, org_id: str) -> tuple[Org, bool]:
        from app_users.models import AppUser

        try:
            return self.get(org_id=org_id), False
        except self.model.DoesNotExist:
            user = AppUser.objects.get_or_create_from_uid(org_id)[0]
            return self.migrate_from_appuser(user), True

    def migrate_from_appuser(self, user: "AppUser") -> Org:
        return self.create_org(
            name=f"{user.first_name()}'s Personal Workspace",
            org_id=user.uid or get_random_doc_id(),
            created_by=user,
            is_personal=True,
            balance=user.balance,
            stripe_customer_id=user.stripe_customer_id,
            subscription=user.subscription,
            low_balance_email_sent_at=user.low_balance_email_sent_at,
            is_paying=user.is_paying,
        )


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

    # billing
    balance = models.IntegerField("bal", default=0)
    is_paying = models.BooleanField("paid", default=False)
    stripe_customer_id = models.CharField(max_length=255, default="", blank=True)
    subscription = models.OneToOneField(
        "payments.Subscription",
        on_delete=models.SET_NULL,
        related_name="org",
        null=True,
        blank=True,
    )
    low_balance_email_sent_at = models.DateTimeField(null=True, blank=True)

    is_personal = models.BooleanField(default=False)

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
            ),
            models.UniqueConstraint(
                "created_by",
                condition=Q(deleted__isnull=True, is_personal=True),
                name="unique_personal_org_per_user",
            ),
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

    def get_owners(self) -> list[OrgMembership]:
        return self.memberships.filter(role=OrgRole.OWNER)

    @db_middleware
    @transaction.atomic
    def add_balance(
        self, amount: int, invoice_id: str, **kwargs
    ) -> "AppUserTransaction":
        """
        Used to add/deduct credits when they are bought or consumed.

        When credits are bought with stripe -- invoice_id is the stripe
        invoice ID.
        When credits are deducted due to a run -- invoice_id is of the
        form "gooey_in_{uuid}"
        """
        from app_users.models import AppUserTransaction

        # if an invoice entry exists
        try:
            # avoid updating twice for same invoice
            return AppUserTransaction.objects.get(invoice_id=invoice_id)
        except AppUserTransaction.DoesNotExist:
            pass

        # select_for_update() is very important here
        # transaction.atomic alone is not enough!
        # It won't lock this row for reads, and multiple threads can update the same row leading incorrect balance
        #
        # Also we're not using .update() here because it won't give back the updated end balance
        org: Org = Org.objects.select_for_update().get(pk=self.pk)
        org.balance += amount
        org.save(update_fields=["balance"])
        kwargs.setdefault("plan", org.subscription and org.subscription.plan)
        return AppUserTransaction.objects.create(
            org=org,
            invoice_id=invoice_id,
            amount=amount,
            end_balance=org.balance,
            **kwargs,
        )

    def get_or_create_stripe_customer(self) -> stripe.Customer:
        customer = self.search_stripe_customer()
        if not customer:
            customer = stripe.Customer.create(
                name=self.created_by.display_name,
                email=self.created_by.email,
                phone=self.created_by.phone,
                metadata={"uid": self.org_id, "org_id": self.org_id, "id": self.pk},
            )
            self.stripe_customer_id = customer.id
            self.save()
        return customer

    def search_stripe_customer(self) -> stripe.Customer | None:
        if not self.org_id:
            return None
        if self.stripe_customer_id:
            try:
                return stripe.Customer.retrieve(self.stripe_customer_id)
            except stripe.error.InvalidRequestError as e:
                if e.http_status != 404:
                    raise
        try:
            customer = stripe.Customer.search(
                query=f'metadata["uid"]:"{self.org_id}"'
            ).data[0]
        except IndexError:
            return None
        else:
            self.stripe_customer_id = customer.id
            self.save()
            return customer

    def get_dollars_spent_this_month(self) -> float:
        today = timezone.now()
        cents_spent = self.transactions.filter(
            created_at__month=today.month,
            created_at__year=today.year,
            amount__gt=0,
        ).aggregate(total=Sum("charged_amount"))["total"]
        return (cents_spent or 0) / 100


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
        from app_users.models import AppUser

        assert self.status == self.Status.PENDING

        invitee = AppUser.objects.get(email=self.invitee_email)
        self.accept(invitee, auto_accepted=True)

        if self.auto_accepted:
            logger.info(f"User {invitee} auto-accepted invitation to org {self.org}")
            send_auto_accepted_email.delay(self.pk)

    def get_url(self):
        from routers.account import invitation_route

        return get_app_route_url(
            invitation_route,
            path_params={"invite_id": self.invite_id, "org_slug": self.org.get_slug()},
        )

    def send_email(self):
        # pre-emptively set last_email_sent_at to avoid sending multiple emails concurrently
        if not self.can_resend_email():
            raise ValidationError("This user has already been invited recently.")

        self.last_email_sent_at = timezone.now()
        self.save(update_fields=["last_email_sent_at"])

        send_invitation_email.delay(invitation_pk=self.pk)

    def accept(self, user: "AppUser", *, auto_accepted: bool = False):
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

    def reject(self, user: "AppUser"):
        self.status = self.Status.REJECTED
        self.status_changed_at = timezone.now()
        self.status_changed_by = user
        self.save()

    def cancel(self, user: "AppUser"):
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
