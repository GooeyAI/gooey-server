from __future__ import annotations

import json
import typing
from datetime import timedelta

import hashids
import stripe
from django.contrib import admin
from django.core import validators
from django.core.exceptions import ValidationError
from django.db import models, transaction, IntegrityError
from django.db.backends.base.schema import logger
from django.db.models.aggregates import Sum
from django.db.models.query_utils import Q
from django.utils import timezone
from django.utils.text import slugify
from safedelete.managers import SafeDeleteQueryset
from safedelete.models import SafeDeleteModel, SOFT_DELETE_CASCADE

from bots.custom_fields import CustomURLField
from daras_ai_v2 import settings, icons
from daras_ai_v2.fastapi_tricks import get_app_route_url
from gooeysite.bg_db_conn import db_middleware
from handles.models import COMMON_EMAIL_DOMAINS
from .tasks import send_added_to_workspace_email, send_invitation_email

if typing.TYPE_CHECKING:
    from app_users.models import AppUser, AppUserTransaction


DEFAULT_WORKSPACE_PHOTO_URL = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/74a37c52-8260-11ee-a297-02420a0001ee/gooey.ai%20-%20A%20pop%20art%20illustration%20of%20robots%20taki...y%20Liechtenstein%20mint%20colour%20is%20main%20city%20Seattle.png"


def validate_workspace_domain_name(value: str):
    if value in COMMON_EMAIL_DOMAINS:
        raise ValidationError("This domain name is reserved")


class WorkspaceRole(models.IntegerChoices):
    OWNER = (1, "Owner")
    ADMIN = (2, "Admin")
    MEMBER = (3, "Member")

    @classmethod
    def display_html(cls, role: WorkspaceRole | int) -> str:
        if isinstance(role, int):
            role = WorkspaceRole(role)

        match role:
            case WorkspaceRole.OWNER:
                return f"{icons.owner} {role.label}"
            case WorkspaceRole.ADMIN:
                return f"{icons.admin} {role.label}"
            case WorkspaceRole.MEMBER:
                return f"{icons.member} {role.label}"


class WorkspaceQuerySet(SafeDeleteQueryset):
    def from_pp_custom_id(self, custom_id: str) -> Workspace:
        try:
            workspace_id = json.loads(custom_id)["workspace_id"]
        except (json.JSONDecodeError, KeyError):
            return self.get_or_create_from_uid(custom_id)[0]
        else:
            return self.get(id=workspace_id)

    def get_or_create_from_uid(self, uid: str) -> tuple[Workspace, bool]:
        from app_users.models import AppUser

        user = AppUser.objects.get(uid=uid)
        return self.get_or_create_from_user(user)

    def get_or_create_from_user(self, user: AppUser) -> tuple[Workspace, bool]:
        kwargs = dict(created_by=user, is_personal=True)
        # The get() needs to be targeted at the write database in order
        # to avoid potential transaction consistency problems.
        self._for_write = True
        try:
            return super().get(**kwargs), False
        except self.model.DoesNotExist:
            try:
                with transaction.atomic():
                    # Try to create an object using passed params.
                    obj = self.model(
                        # copy fields from existing user
                        balance=user.balance,
                        stripe_customer_id=user.stripe_customer_id,
                        subscription=user.subscription,
                        low_balance_email_sent_at=user.low_balance_email_sent_at,
                        is_paying=user.is_paying,
                        **kwargs,
                    )
                    obj.create_with_owner()
                    return obj, True
            except IntegrityError:
                try:
                    return super().get(**kwargs), False
                except self.model.DoesNotExist:
                    pass
                raise


class Workspace(SafeDeleteModel):
    _safedelete_policy = SOFT_DELETE_CASCADE

    name = models.CharField(max_length=100, blank=True, default="")
    created_by = models.ForeignKey(
        "app_users.AppUser",
        on_delete=models.CASCADE,
        related_name="created_workspaces",
    )

    domain_name = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        db_index=True,
        validators=[
            validators.DomainNameValidator(),
            validate_workspace_domain_name,
        ],
    )
    onedrive_user_name = models.CharField(
        blank=True,
        default="",
        max_length=100,
        help_text="Onedrive Registered Account Name",
        editable=True,
    )

    onedrive_access_token = models.TextField(
        blank=True,
        default="",
        help_text="Onedrive OAuth2 access token",
        editable=True,
    )
    onedrive_refresh_token = models.TextField(
        blank=True,
        default="",
        help_text="OneDrive OAuth2 refresh token",
        editable=True,
    )

    # profile
    handle = models.OneToOneField(
        "handles.Handle",
        on_delete=models.SET_NULL,
        related_name="workspace",
        null=True,
        blank=True,
    )
    photo_url = CustomURLField(null=True, blank=True)
    banner_url = CustomURLField(null=True, blank=True)
    description = models.TextField(blank=True, default="")

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

    objects = WorkspaceQuerySet.as_manager()

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
            return f"[Deleted] {self.display_name()}"
        else:
            return self.display_name()

    def clean(self) -> None:
        if not self.is_personal and not self.name:
            raise ValidationError("Team name is required for workspaces")
        return super().clean()

    def get_slug(self):
        return slugify(self.display_name())

    @transaction.atomic()
    def create_with_owner(self):
        # free credits for first team created by a user
        # Workspace.all_objects is important to include deleted workspaces
        if (
            not self.is_personal
            and not self.balance
            and Workspace.all_objects.filter(created_by=self.created_by).count() <= 1
        ):
            self.balance = settings.FIRST_WORKSPACE_FREE_CREDITS
        self.id = None
        # in a transaction, let the database handle constraints
        self.full_clean(validate_unique=False, validate_constraints=False)
        self.save()
        WorkspaceMembership.objects.create(
            workspace=self,
            user=self.created_by,
            role=WorkspaceRole.OWNER,
        )

    def get_owners(self) -> models.QuerySet[AppUser]:
        from app_users.models import AppUser

        return AppUser.objects.filter(
            workspace_memberships__workspace=self,
            workspace_memberships__role=WorkspaceRole.OWNER,
            workspace_memberships__deleted__isnull=True,
        )

    def get_admins(self) -> models.QuerySet[AppUser]:
        from app_users.models import AppUser

        return AppUser.objects.filter(
            workspace_memberships__workspace=self,
            workspace_memberships__role=WorkspaceRole.ADMIN,
            workspace_memberships__deleted__isnull=True,
        )

    @db_middleware
    @transaction.atomic
    def add_balance(
        self, amount: int, invoice_id: str, *, user: AppUser | None = None, **kwargs
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

        if workspace.subscription:
            kwargs.setdefault("plan", workspace.subscription.plan)
        if user:
            kwargs.setdefault("user", user)
        elif workspace.is_personal:
            kwargs.setdefault("user", workspace.created_by)

        try:
            return AppUserTransaction.objects.create(
                workspace=workspace,
                invoice_id=invoice_id,
                amount=amount,
                end_balance=workspace.balance,
                **kwargs,
            )
        except IntegrityError:
            try:
                return AppUserTransaction.objects.get(invoice_id=invoice_id)
            except AppUserTransaction.DoesNotExist:
                pass
            raise

    def get_or_create_stripe_customer(self) -> stripe.Customer:
        customer = None

        # search by saved customer ID
        if self.stripe_customer_id:
            try:
                candidate = stripe.Customer.retrieve(self.stripe_customer_id)
                if not candidate.get("deleted"):
                    customer = candidate
            except stripe.InvalidRequestError as e:
                if e.http_status != 404:
                    raise

        # search by metadata saved in stripe
        if not customer:
            query = f'metadata["workspace_id"]:"{self.id}"'
            if self.is_personal:
                query += f' or metadata["id"]:"{self.created_by.id}" or metadata["uid"]:"{self.created_by.uid}"'

            for candidate in stripe.Customer.search(query=query).data:
                if candidate.get("deleted"):
                    continue
                else:
                    customer = candidate
                    break

        # create a new customer if not found
        if not customer:
            customer = stripe.Customer.create(
                name=self.display_name(),
                email=self.created_by.email,
                phone=self.created_by.phone_number,
                metadata=self.get_stripe_customer_metadata(),
            )

        # update the saved customer ID
        if self.stripe_customer_id != customer.id:
            self.stripe_customer_id = customer.id
            self.save(update_fields=["stripe_customer_id"])

        # update the saved metadata in stripe
        if not customer.get("metadata", {}).get("workspace_id"):
            customer = stripe.Customer.modify(
                id=customer.id, metadata=self.get_stripe_customer_metadata()
            )

        return customer

    def get_stripe_customer_metadata(self) -> dict:
        metadata = dict(workspace_id=str(self.id))
        if self.is_personal:
            metadata.update(
                dict(id=str(self.created_by.id), uid=str(self.created_by.uid))
            )
        return metadata

    def get_dollars_spent_this_month(self) -> float:
        today = timezone.now()
        cents_spent = self.transactions.filter(
            created_at__month=today.month,
            created_at__year=today.year,
            amount__gt=0,
        ).aggregate(total=Sum("charged_amount"))["total"]
        return (cents_spent or 0) / 100

    def get_pp_custom_id(self) -> str:
        return json.dumps(dict(workspace_id=self.id))

    def display_html(self, current_user: AppUser | None = None) -> str:
        return f"{self.html_icon()}&nbsp;&nbsp;{self.display_name(current_user)}"

    def display_name(self, current_user: AppUser | None = None) -> str:
        if self.name:
            return self.name
        elif (
            self.is_personal and current_user and self.created_by_id == current_user.id
        ):
            return f"{current_user.full_name()} (Personal)"
        elif self.is_personal:
            return self.created_by.full_name()
        else:
            return f"{self.created_by.first_name_possesive()} Workspace"

    def html_icon(self) -> str:
        if photo_url := self.get_photo():
            return f'<img src="{photo_url}" style="height: 25px; width: 25px; object-fit: cover; border-radius: 12.5px;">'
        if self.is_personal:
            return icons.home
        else:
            return icons.company

    def get_photo(self) -> str:
        if self.is_personal:
            return self.created_by.get_photo()
        else:
            return self.photo_url or DEFAULT_WORKSPACE_PHOTO_URL

    def get_banner_url(self) -> str | None:
        if self.is_personal:
            return self.created_by.banner_url
        else:
            return self.banner_url

    def get_description(self) -> str | None:
        if self.is_personal:
            return self.created_by.bio
        else:
            return self.description

    def add_domain_members(self):
        from app_users.models import AppUser

        if not self.domain_name:
            return
        current_user = self.get_owners().first()
        if not current_user:
            return
        for user_email in (
            AppUser.objects.filter(email__iendswith=self.domain_name)
            .exclude(workspace_memberships__workspace=self)
            .values_list("email", flat=True)
        )[:50]:
            WorkspaceInvite.objects.create_and_send_invite(
                workspace=self,
                email=user_email,
                current_user=current_user,
                defaults=dict(role=WorkspaceRole.MEMBER),
            )


class WorkspaceMembership(SafeDeleteModel):
    workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        "app_users.AppUser",
        on_delete=models.CASCADE,
        related_name="workspace_memberships",
    )
    invite = models.ForeignKey(
        "WorkspaceInvite",
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

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "user"],
                condition=Q(deleted__isnull=True),
                name="unique_workspace_user",
            )
        ]
        indexes = [
            models.Index(fields=["workspace", "role", "deleted"]),
        ]

    def __str__(self):
        return f"{self.get_role_display()} - {self.user} ({self.workspace})"

    def clean(self) -> None:
        if self.workspace.is_personal and self.user_id != self.workspace.created_by_id:
            raise ValidationError("You cannot add users to a personal workspace")
        return super().clean()

    def can_edit_workspace(self):
        # workspace metadata, billing, etc.
        return self.role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN)

    def can_leave_workspace(self):
        return not (
            self.workspace.is_personal and self.workspace.created_by_id == self.user_id
        )

    def can_delete_workspace(self):
        return not self.workspace.is_personal and self.role == WorkspaceRole.OWNER

    def has_higher_role_than(self, other: "WorkspaceMembership"):
        # creator > owner > admin > member
        match other.role:
            case WorkspaceRole.OWNER:
                return self.workspace.created_by_id == other.id and self.id != other.id
            case WorkspaceRole.ADMIN:
                return self.role == WorkspaceRole.OWNER
            case WorkspaceRole.MEMBER:
                return self.role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN)

    def can_change_role(self, other: "WorkspaceMembership"):
        return self.has_higher_role_than(other)

    def can_kick(self, other: "WorkspaceMembership"):
        return (
            self.has_higher_role_than(other)
            and not self.workspace.created_by_id == other.id
        )

    def can_transfer_ownership(self):
        return self.role == WorkspaceRole.OWNER

    def can_invite(self):
        return (
            self.role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN)
            and not self.workspace.is_personal
        )


class WorkspaceInviteQuerySet(models.QuerySet):
    def create_and_send_invite(
        self,
        *,
        workspace: Workspace,
        email: str,
        current_user: typing.Optional["AppUser"] = None,
        defaults: dict | None = None,
    ) -> "WorkspaceInvite":
        from app_users.models import AppUser

        if workspace.memberships.filter(user__email=email).exists():
            raise ValidationError(f"{email} is already a member of this workspace")

        if defaults is None:
            defaults = {}
        if current_user:
            defaults["created_by"] = current_user

        with transaction.atomic():
            invite, created = self.get_or_create(
                workspace=workspace, email=email, defaults=defaults
            )
            invite.full_clean()

            if not created and invite.status != WorkspaceInvite.Status.PENDING:
                invite.status = WorkspaceInvite.Status.PENDING
                invite.save(update_fields=["status"])

        try:
            invitee = AppUser.objects.get(email=invite.email)
        except AppUser.DoesNotExist:
            invite.send_email()
        else:
            invite.accept(
                invitee,
                updated_by=current_user or invite.created_by,
                auto_accepted=True,
            )
            logger.info(
                f"User {invitee} auto-accepted invitation to workspace {invite.workspace}"
            )
            send_added_to_workspace_email.delay(invite_id=invite.id, user_id=invitee.id)

        return invite


class WorkspaceInvite(models.Model):
    class Status(models.IntegerChoices):
        PENDING = 1
        ACCEPTED = 2
        CANCELED = 3

    workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, related_name="invites"
    )
    email = models.EmailField()
    role = models.IntegerField(
        choices=WorkspaceRole.choices, default=WorkspaceRole.MEMBER
    )

    clicks = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(
        "app_users.AppUser",
        on_delete=models.CASCADE,
        related_name="sent_invites",
    )
    updated_by = models.ForeignKey(
        "app_users.AppUser",
        on_delete=models.CASCADE,
        related_name="+",
        null=True,
        blank=True,
    )

    status = models.IntegerField(choices=Status.choices, default=Status.PENDING)
    auto_accepted = models.BooleanField(default=False)

    last_email_sent_at = models.DateTimeField(null=True, blank=True, default=None)

    objects = WorkspaceInviteQuerySet.as_manager()

    api_hashids = hashids.Hashids(salt=settings.HASHIDS_API_SALT + "/invites")

    class Meta:
        unique_together = [
            ("workspace", "email"),
        ]

    def __str__(self):
        return f"{self.email} - {self.workspace} ({self.get_status_display()})"

    def clean(self) -> None:
        if self.workspace.is_personal:
            raise ValidationError("You cannot invite users to a personal workspace")
        return super().clean()

    @admin.display(description="Expired")
    def has_expired(self):
        if not self.updated_at:
            return False
        return (timezone.now() - self.updated_at) > timedelta(
            days=settings.WORKSPACE_INVITE_EXPIRY_DAYS
        )

    def get_invite_url(self):
        from routers.account import invitation_route

        return get_app_route_url(
            invitation_route,
            path_params=dict(
                invite_id=self.get_invite_id(),
                email=self.email,
                workspace_slug=self.workspace.get_slug(),
            ),
        )

    def get_invite_id(self) -> str:
        return self.api_hashids.encode(self.id)

    def can_resend_email(self):
        if not self.last_email_sent_at:
            return True

        return timezone.now() - self.last_email_sent_at > timedelta(
            seconds=settings.WORKSPACE_INVITE_EMAIL_COOLDOWN_INTERVAL
        )

    def send_email(self):
        if not self.can_resend_email():
            raise ValidationError("This user has already been invited recently.")

        send_invitation_email.delay(invitation_pk=self.pk)

    @transaction.atomic
    def accept(
        self,
        invitee: AppUser,
        *,
        updated_by: AppUser | None = None,
        auto_accepted: bool = False,
    ) -> tuple[WorkspaceMembership, bool]:
        """
        Raises: ValidationError
        """
        assert (
            invitee.email and invitee.email.lower() == self.email.lower()
        ), "Email mismatch"

        membership, created = WorkspaceMembership.objects.get_or_create(
            workspace=self.workspace,
            user=invitee,
            defaults=dict(invite=self, role=self.role),
        )
        if not created:
            return membership, created

        # can't accept an invite that is already accepted / rejected / canceled
        if self.status != self.Status.PENDING:
            raise ValidationError(
                f"This invitation has been {self.get_status_display().lower()}."
            )

        if self.has_expired():
            raise ValidationError(
                "This invitation has expired. Please ask your team admin to send a new one."
            )

        self.updated_by = updated_by
        self.status = self.Status.ACCEPTED
        self.auto_accepted = auto_accepted

        self.full_clean()
        self.save(update_fields=["status", "updated_by", "auto_accepted", "updated_at"])

        return membership, created

    def cancel(self, user: "AppUser"):
        self.status = self.Status.CANCELED
        self.updated_by = user
        self.save()
