from __future__ import annotations

import re
import typing
from datetime import timedelta

import stripe
from django.db.models.aggregates import Sum
from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.db.backends.base.schema import logger
from django.db.models.query_utils import Q
from django.utils import timezone
from django.utils.text import slugify
from safedelete.managers import SafeDeleteManager
from safedelete.models import SafeDeleteModel, SOFT_DELETE_CASCADE

from bots.custom_fields import CustomURLField
from daras_ai_v2 import settings
from daras_ai_v2.fastapi_tricks import get_app_route_url
from daras_ai_v2.crypto import get_random_doc_id
from gooeysite.bg_db_conn import db_middleware
from .tasks import send_auto_accepted_email, send_invitation_email


if typing.TYPE_CHECKING:
    from app_users.models import AppUser, AppUserTransaction


WORKSPACE_DOMAIN_NAME_RE = re.compile(r"^[a-z0-9]+([\-\.]{1}[a-z0-9]+)*\.[a-z]+$")


def validate_workspace_domain_name(value):
    from handles.models import COMMON_EMAIL_DOMAINS

    if not WORKSPACE_DOMAIN_NAME_RE.fullmatch(value):
        raise ValidationError("Invalid domain name")

    if value in COMMON_EMAIL_DOMAINS:
        raise ValidationError("This domain name is reserved")


class WorkspaceRole(models.IntegerChoices):
    OWNER = 1
    ADMIN = 2
    MEMBER = 3


class WorkspaceManager(SafeDeleteManager):
    def create_workspace(
        self,
        *,
        created_by: "AppUser",
        balance: int | None = None,
        **kwargs,
    ) -> Workspace:
        workspace = self.model(
            created_by=created_by,
            balance=balance,
            **kwargs,
        )
        if (
            balance is None
            and Workspace.all_objects.filter(created_by=created_by).count() <= 1
        ):
            # set some balance for first team created by user
            # Workspace.all_objects is important to include deleted workspaces
            workspace.balance = settings.FIRST_WORKSPACE_FREE_CREDITS

        workspace.full_clean()
        workspace.save()
        workspace.add_member(
            created_by,
            role=WorkspaceRole.OWNER,
        )
        return workspace

    def get_or_create_from_uid(self, uid: str) -> tuple[Workspace, bool]:
        workspace = Workspace.objects.filter(
            is_personal=True, created_by__uid=uid
        ).first()
        if workspace:
            return workspace, False

        user, _ = AppUser.objects.get_or_create_from_uid(uid)
        workspace = self.migrate_from_appuser(user)
        return workspace, True

    def migrate_from_appuser(self, user: "AppUser") -> Workspace:
        return self.create_workspace(
            name=f"{user.first_name()}'s Personal Workspace",
            created_by=user,
            is_personal=True,
            balance=user.balance,
            stripe_customer_id=user.stripe_customer_id,
            subscription=user.subscription,
            low_balance_email_sent_at=user.low_balance_email_sent_at,
            is_paying=user.is_paying,
        )

    def get_dollars_spent_this_month(self) -> float:
        today = timezone.now()
        cents_spent = self.transactions.filter(
            created_at__month=today.month,
            created_at__year=today.year,
            amount__gt=0,
        ).aggregate(total=Sum("charged_amount"))["total"]
        return (cents_spent or 0) / 100


class Workspace(SafeDeleteModel):
    _safedelete_policy = SOFT_DELETE_CASCADE

    name = models.CharField(max_length=100)
    created_by = models.ForeignKey(
        "app_users.appuser",
        on_delete=models.CASCADE,
    )

    logo = CustomURLField(null=True, blank=True)
    domain_name = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        validators=[
            validate_workspace_domain_name,
        ],
    )

    # billing
    balance = models.IntegerField("bal", default=0)
    is_paying = models.BooleanField("paid", default=False)
    stripe_customer_id = models.CharField(max_length=255, default="", blank=True)
    subscription = models.OneToOneField(
        "payments.Subscription",
        on_delete=models.SET_NULL,
        related_name="workspace",
        null=True,
        blank=True,
    )
    low_balance_email_sent_at = models.DateTimeField(null=True, blank=True)

    is_personal = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = WorkspaceManager()

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
                name="unique_personal_workspace_per_user",
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
        self,
        user: "AppUser",
        role: WorkspaceRole,
        invitation: "WorkspaceInvitation | None" = None,
    ):
        WorkspaceMembership(
            workspace=self,
            user=user,
            role=role,
            invitation=invitation,
        ).save()

    def invite_user(
        self,
        *,
        invitee_email: str,
        inviter: "AppUser",
        role: WorkspaceRole,
        auto_accept: bool = False,
    ) -> "WorkspaceInvitation":
        """
        auto_accept: If True, the user will be automatically added if they have an account
        """
        for member in self.memberships.all().select_related("user"):
            if member.user.email == invitee_email:
                raise ValidationError(f"{member.user} is already a member of this team")

        for invitation in self.invitations.filter(
            status=WorkspaceInvitation.Status.PENDING
        ):
            if invitation.invitee_email == invitee_email:
                raise ValidationError(
                    f"{invitee_email} was already invited to this team"
                )

        invitation = WorkspaceInvitation(
            invite_id=get_random_doc_id(),
            workspace=self,
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

    def get_owners(self) -> models.QuerySet[WorkspaceMembership]:
        return self.memberships.filter(role=WorkspaceRole.OWNER)

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
        workspace: Workspace = Workspace.objects.select_for_update().get(pk=self.pk)
        workspace.balance += amount
        workspace.save(update_fields=["balance"])
        kwargs.setdefault(
            "plan", workspace.subscription and workspace.subscription.plan
        )
        return AppUserTransaction.objects.create(
            workspace=workspace,
            user=workspace.created_by if workspace.is_personal else None,
            invoice_id=invoice_id,
            amount=amount,
            end_balance=workspace.balance,
            **kwargs,
        )

    def get_or_create_stripe_customer(self) -> stripe.Customer:
        customer = self.search_stripe_customer()
        if not customer:
            metadata = {"workspace_id": self.id}
            if self.is_personal:
                metadata["uid"] = self.created_by.uid

            customer = stripe.Customer.create(
                name=self.created_by.display_name,
                email=self.created_by.email,
                phone=self.created_by.phone_number,
                metadata=metadata,
            )
            self.stripe_customer_id = customer.id
            self.save()
        return customer

    def search_stripe_customer(self) -> stripe.Customer | None:
        if self.stripe_customer_id:
            try:
                return stripe.Customer.retrieve(self.stripe_customer_id)
            except stripe.InvalidRequestError as e:
                if e.http_status != 404:
                    raise

        try:
            customer = stripe.Customer.search(
                query=f'metadata["workspace_id"]:"{self.id}"'
            ).data[0]
        except IndexError:
            customer = self.is_personal and self.created_by.search_stripe_customer()
            if not customer:
                return None

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


class WorkspaceMembership(SafeDeleteModel):
    workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        "app_users.AppUser",
        on_delete=models.CASCADE,
        related_name="workspace_memberships",
    )
    invitation = models.OneToOneField(
        "WorkspaceInvitation",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        default=None,
        related_name="membership",
    )

    role = models.IntegerField(
        choices=WorkspaceRole.choices, default=WorkspaceRole.MEMBER
    )

    created_at = models.DateTimeField(auto_now_add=True)  # same as joining date
    updated_at = models.DateTimeField(auto_now=True)

    objects = SafeDeleteManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "user"],
                condition=Q(deleted__isnull=True),
                name="unique_workspace_user",
            )
        ]

    def __str__(self):
        return f"{self.get_role_display()} - {self.user} ({self.workspace})"

    def can_edit_workspace_metadata(self):
        return self.role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN)

    def can_delete_workspace(self):
        return self.role == WorkspaceRole.OWNER

    def has_higher_role_than(self, other: "WorkspaceMembership"):
        # creator > owner > admin > member
        match other.role:
            case WorkspaceRole.OWNER:
                return self.workspace.created_by == WorkspaceRole.OWNER
            case WorkspaceRole.ADMIN:
                return self.role == WorkspaceRole.OWNER
            case WorkspaceRole.MEMBER:
                return self.role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN)

    def can_change_role(self, other: "WorkspaceMembership"):
        return self.has_higher_role_than(other)

    def can_kick(self, other: "WorkspaceMembership"):
        return self.has_higher_role_than(other)

    def can_transfer_ownership(self):
        return self.role == WorkspaceRole.OWNER

    def can_invite(self):
        return self.role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN)


class WorkspaceInvitation(SafeDeleteModel):
    class Status(models.IntegerChoices):
        PENDING = 1
        ACCEPTED = 2
        REJECTED = 3
        CANCELED = 4
        EXPIRED = 5

    invite_id = models.CharField(max_length=100, unique=True)
    invitee_email = models.EmailField()

    workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, related_name="invitations"
    )
    inviter = models.ForeignKey(
        "app_users.AppUser", on_delete=models.CASCADE, related_name="sent_invitations"
    )

    status = models.IntegerField(choices=Status.choices, default=Status.PENDING)
    auto_accepted = models.BooleanField(default=False)
    role = models.IntegerField(
        choices=WorkspaceRole.choices, default=WorkspaceRole.MEMBER
    )

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
        return f"{self.invitee_email} - {self.workspace} ({self.get_status_display()})"

    def has_expired(self):
        return self.status == self.Status.EXPIRED or (
            timezone.now() - (self.last_email_sent_at or self.created_at)
            > timedelta(days=settings.WORKSPACE_INVITATION_EXPIRY_DAYS)
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
            logger.info(
                f"User {invitee} auto-accepted invitation to workspace {self.workspace}"
            )
            send_auto_accepted_email.delay(self.pk)

    def get_url(self):
        from routers.account import invitation_route

        return get_app_route_url(
            invitation_route,
            path_params={
                "invite_id": self.invite_id,
                "workspace_slug": self.workspace.get_slug(),
            },
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

        if self.workspace.memberships.filter(user_id=user.pk).exists():
            raise ValidationError(f"User is already a member of this team.")

        self.status = self.Status.ACCEPTED
        self.auto_accepted = auto_accepted
        self.status_changed_at = timezone.now()
        self.status_changed_by = user

        self.full_clean()

        with transaction.atomic():
            user.workspace_memberships.all().delete()  # delete current memberships
            self.workspace.add_member(
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
            seconds=settings.WORKSPACE_INVITATION_EMAIL_COOLDOWN_INTERVAL
        )
