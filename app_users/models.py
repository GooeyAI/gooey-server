import hashlib
import typing
from functools import cached_property

import requests
from django.db import models, IntegrityError, transaction
from django.utils import timezone
from firebase_admin import auth
from furl import furl
from phonenumber_field.modelfields import PhoneNumberField

from bots.custom_fields import CustomURLField, StrippedTextField
from daras_ai.image_input import upload_file_from_bytes, guess_ext_from_response
from daras_ai_v2 import settings
from handles.models import Handle
from payments.plans import PricingPlan

if typing.TYPE_CHECKING:
    from workspaces.models import Workspace
    from phonenumber_field.phonenumber import PhoneNumber


class AppUserQuerySet(models.QuerySet):
    def get_or_create_from_uid(
        self, uid: str, defaults=None, **kwargs
    ) -> tuple["AppUser", bool]:
        kwargs.setdefault("uid", uid)
        # The get() needs to be targeted at the write database in order
        # to avoid potential transaction consistency problems.
        self._for_write = True
        try:
            return super().get(**kwargs), False
        except self.model.DoesNotExist:
            firebase_user = auth.get_user(uid)
            # Try to create an object using passed params.
            try:
                user = self.model(**kwargs)
                user.copy_from_firebase_user(firebase_user)
                return user, True
            except IntegrityError:
                try:
                    return self.get(**kwargs), False
                except self.model.DoesNotExist:
                    pass
                raise

    def get_or_create_from_email(
        self, email: str, defaults=None, **kwargs
    ) -> tuple["AppUser", bool]:
        kwargs.setdefault("email", email)
        # The get() needs to be targeted at the write database in order
        # to avoid potential transaction consistency problems.
        self._for_write = True
        try:
            return super().get(**kwargs), False
        except self.model.DoesNotExist:
            firebase_user = get_or_create_firebase_user_by_email(email)[0]
            # Try to create an object using passed params.
            try:
                user = self.model(**kwargs)
                user.copy_from_firebase_user(firebase_user)
                return user, True
            except IntegrityError:
                try:
                    return self.get(**kwargs), False
                except self.model.DoesNotExist:
                    pass
                raise


def get_or_create_firebase_user_by_email(email: str) -> tuple[auth.UserRecord, bool]:
    try:
        return auth.get_user_by_email(email), False
    except auth.UserNotFoundError:
        try:
            return auth.create_user(email=email), True
        except auth.EmailAlreadyExistsError:
            try:
                return auth.get_user_by_email(email), False
            except auth.UserNotFoundError:
                pass
            raise


class PaymentProvider(models.IntegerChoices):
    STRIPE = 1, "Stripe"
    PAYPAL = 2, "PayPal"


class AppUser(models.Model):
    uid = models.CharField(max_length=255, unique=True)

    display_name = models.TextField("name", blank=True)
    email = models.EmailField(null=True, blank=True)
    phone_number = PhoneNumberField(null=True, blank=True)
    is_anonymous = models.BooleanField()
    is_disabled = models.BooleanField(default=False)
    photo_url = CustomURLField(default="", blank=True)

    balance = models.IntegerField(
        "bal", help_text="[Deprecated]", default=None, null=True, blank=True
    )
    stripe_customer_id = models.CharField(
        max_length=255, default="", blank=True, help_text="[Deprecated]"
    )
    is_paying = models.BooleanField("paid", default=False, help_text="[Deprecated]")
    low_balance_email_sent_at = models.DateTimeField(
        null=True, blank=True, help_text="[Deprecated]"
    )
    subscription = models.OneToOneField(
        "payments.Subscription",
        on_delete=models.SET_NULL,
        related_name="user",
        null=True,
        blank=True,
        help_text="[Deprecated]",
    )

    created_at = models.DateTimeField(
        "created", editable=False, blank=True, default=timezone.now
    )
    updated_at = models.DateTimeField(auto_now=True)
    upgraded_from_anonymous_at = models.DateTimeField(null=True, blank=True)

    disable_safety_checker = models.BooleanField(default=False)

    banner_url = CustomURLField(blank=True, default="")
    bio = StrippedTextField(blank=True, default="")
    company = models.CharField(max_length=255, blank=True, default="")
    github_username = models.CharField(max_length=255, blank=True, default="")
    website_url = CustomURLField(blank=True, default="")

    disable_rate_limits = models.BooleanField(default=False)

    objects = AppUserQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=["email"]),
        ]

    def __str__(self):
        return f"{self.display_name} ({self.email or self.phone_number or self.uid})"

    def first_name_possesive(self, fallback: str = "My") -> str:
        first_name = self.first_name(fallback=fallback)
        if first_name == "My":
            return first_name
        elif first_name.endswith("s"):
            return first_name + "'"
        else:
            return first_name + "'s"

    def first_name(self, *, fallback: str = "Anon") -> str:
        return self.full_name(fallback=fallback).split(" ")[0]

    def full_name(
        self,
        *,
        current_user: typing.Optional["AppUser"] = None,
        fallback: str = "Anonymous",
    ) -> str:
        if self.display_name:
            name = self.display_name
        elif self.email:
            name = self.email.split("@")[0]
        elif self.phone_number:
            name = obscure_phone_number(self.phone_number)
        else:
            return fallback
        if current_user and self == current_user:
            name += " (You)"
        return name

    def copy_from_firebase_user(self, user: auth.UserRecord) -> "AppUser":
        # copy data from firebase user
        self.uid = user.uid
        self.is_disabled = user.disabled
        self.display_name = user.display_name or ""
        if user.email:
            self.email = str(user.email)
        if user.phone_number:
            self.phone_number = str(user.phone_number)
        self.created_at = timezone.datetime.fromtimestamp(
            user.user_metadata.creation_timestamp / 1000
        )

        # retrieve photo from firebase and upload to cloud storage
        if user.photo_url:
            response = requests.get(user.photo_url)
            if response.ok:
                ext = guess_ext_from_response(response)
                self.photo_url = upload_file_from_bytes(
                    f"user_photo_{user.uid}{ext}", response.content
                )

        # firebase doesnt provide is_anonymous field, so we have to infer it
        is_anonymous_now = not (user.display_name or user.email or user.phone_number)
        if not is_anonymous_now:  # user is not anonymous, they might have upgraded
            if self.is_anonymous is None:
                # is_anonymous is not set, assume user upgraded at time of creation
                self.upgraded_from_anonymous_at = self.created_at
            elif self.is_anonymous:
                # user upgraded from anonymous to permanent, record this event
                self.upgraded_from_anonymous_at = timezone.now()
        self.is_anonymous = is_anonymous_now

        # get existing balance or set free credits
        if self.is_anonymous:
            self.balance = settings.ANON_USER_FREE_CREDITS
        elif any(
            provider.provider_id != "password" for provider in user.provider_data
        ) or (
            "+" not in self.email
            and self.email.split("@")[-1].lower() in settings.VERIFIED_EMAIL_DOMAINS
        ):
            self.balance = settings.VERIFIED_EMAIL_USER_FREE_CREDITS
        else:
            self.balance = 0

        self.save()
        workspace, _ = self.get_or_create_personal_workspace()

        if not self.is_anonymous:
            with transaction.atomic():
                if handle := Handle.create_default_for_workspace(workspace):
                    workspace.handle = handle
                    workspace.save()

        return self

    def get_or_create_personal_workspace(self) -> tuple["Workspace", bool]:
        from workspaces.models import Workspace

        return Workspace.objects.get_or_create_from_user(self)

    @cached_property
    def cached_workspaces(self) -> list["Workspace"]:
        from workspaces.models import Workspace

        return list(
            Workspace.objects.filter(
                memberships__user=self, memberships__deleted__isnull=True
            ).order_by("-is_personal", "-created_at")
        ) or [self.get_or_create_personal_workspace()[0]]

    def get_handle(self) -> Handle | None:
        workspace, _ = self.get_or_create_personal_workspace()
        return workspace.handle

    def get_anonymous_token(self):
        return auth.create_custom_token(self.uid).decode()

    def get_photo(self) -> str:
        return self.photo_url or get_placeholder_profile_image(self.uid)

    def is_admin(self) -> bool:
        return bool(self.email and self.email in settings.ADMIN_EMAILS)


class TransactionReason(models.IntegerChoices):
    DEDUCT = 1, "Deduct"
    ADDON = 2, "Addon"

    SUBSCRIBE = 3, "Subscribe"
    SUBSCRIPTION_CREATE = 4, "Sub-Create"
    SUBSCRIPTION_CYCLE = 5, "Sub-Cycle"
    SUBSCRIPTION_UPDATE = 6, "Sub-Update"

    AUTO_RECHARGE = 7, "Auto-Recharge"


class AppUserTransaction(models.Model):
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    user = models.ForeignKey(
        "AppUser",
        on_delete=models.CASCADE,
        related_name="transactions",
        null=True,
        default=None,
        blank=True,
    )
    invoice_id = models.CharField(
        max_length=255,
        unique=True,
        help_text="The Payment Provider's Invoice ID for this transaction.<br>"
        "For Gooey, this will be of the form 'gooey_in_{uuid}'",
    )

    amount = models.IntegerField(
        help_text="The amount (Gooey credits) added/deducted in this transaction.<br>"
        "Positive for credits added, negative for credits deducted."
    )
    end_balance = models.IntegerField(
        help_text="The end balance (Gooey credits) of the user after this transaction"
    )

    payment_provider = models.IntegerField(
        choices=PaymentProvider.choices,
        null=True,
        blank=True,
        default=None,
        help_text="The payment provider used for this transaction.<br>"
        "If this is provided, the Charged Amount should also be provided.",
    )
    charged_amount = models.PositiveIntegerField(
        help_text="The charged dollar amount in the currency’s smallest unit.<br>"
        "E.g. for 10 USD, this would be of 1000 (that is, 1000 cents).<br>"
        "<a href='https://stripe.com/docs/currencies'>Learn More</a>",
        default=0,
    )

    reason = models.IntegerField(
        choices=TransactionReason.choices,
        help_text="The reason for this transaction.<br><br>"
        f"{TransactionReason.DEDUCT.label}: Credits deducted due to a run.<br>"
        f"{TransactionReason.ADDON.label}: User purchased an add-on.<br>"
        f"{TransactionReason.SUBSCRIBE.label}: Applies to subscriptions where no distinction was made between create, update and cycle.<br>"
        f"{TransactionReason.SUBSCRIPTION_CREATE.label}: A subscription was created.<br>"
        f"{TransactionReason.SUBSCRIPTION_CYCLE.label}: A subscription advanced into a new period.<br>"
        f"{TransactionReason.SUBSCRIPTION_UPDATE.label}: A subscription was updated.<br>"
        f"{TransactionReason.AUTO_RECHARGE.label}: Credits auto-recharged due to low balance.",
    )
    plan = models.IntegerField(
        choices=PricingPlan.db_choices(),
        help_text="User's plan at the time of this transaction.",
        null=True,
        blank=True,
        default=None,
    )

    created_at = models.DateTimeField(editable=False, blank=True, default=timezone.now)

    class Meta:
        verbose_name = "Transaction"
        constraints = [
            models.CheckConstraint(
                # either user or workspace must be present
                check=models.Q(user__isnull=False) | models.Q(workspace__isnull=False),
                name="user_or_workspace_present",
            )
        ]
        indexes = [
            models.Index(fields=["workspace", "amount", "-created_at"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"{self.invoice_id} ({self.amount})"

    def save(self, *args, **kwargs):
        if self.reason is None:
            if self.amount <= 0:
                self.reason = TransactionReason.DEDUCT
            else:
                self.reason = TransactionReason.ADDON
        super().save(*args, **kwargs)

    def reason_note(self) -> str:
        match self.reason:
            case (
                TransactionReason.SUBSCRIPTION_CREATE
                | TransactionReason.SUBSCRIPTION_CYCLE
                | TransactionReason.SUBSCRIPTION_UPDATE
                | TransactionReason.SUBSCRIBE
            ):
                ret = "Subscription payment"
                if self.plan:
                    ret += f": {PricingPlan.from_db_value(self.plan).title}"
                return ret
            case TransactionReason.AUTO_RECHARGE:
                return "Auto recharge"
            case TransactionReason.ADDON:
                return "Addon purchase"
            case TransactionReason.DEDUCT:
                return "Run deduction"

    def payment_provider_url(self) -> str | None:
        match self.payment_provider:
            case PaymentProvider.STRIPE:
                return str(
                    furl("https://dashboard.stripe.com/invoices/") / self.invoice_id
                )
            case PaymentProvider.PAYPAL:
                return str(
                    furl("https://www.paypal.com/unifiedtransactions/details/payment/")
                    / self.invoice_id
                )


def get_placeholder_profile_image(seed: str) -> str:
    hash = hashlib.md5(seed.encode()).hexdigest()
    return f"https://gravatar.com/avatar/{hash}?d=robohash&size=150"


def obscure_phone_number(phone_number: "PhoneNumber") -> str:
    """
    Obscure the phone number by replacing the middle digits with asterisks.
    """
    country_code = phone_number.country_code
    national_number = str(phone_number.national_number)

    return "".join(
        [
            (country_code and f"+{country_code}" or ""),
            national_number[:3],
            "*" * len(national_number[3:-3]),
            national_number[-3:],
        ]
    )
