import requests
import stripe
from django.db import models, IntegrityError, transaction
from django.utils import timezone
from firebase_admin import auth
from phonenumber_field.modelfields import PhoneNumberField

from bots.custom_fields import CustomURLField
from daras_ai.image_input import upload_file_from_bytes, guess_ext_from_response
from daras_ai_v2 import settings, db
from gooeysite.bg_db_conn import db_middleware


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
                user.save()
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
                user.save()
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


class AppUser(models.Model):
    uid = models.CharField(max_length=255, unique=True)

    display_name = models.TextField("name", blank=True)
    email = models.EmailField(null=True, blank=True)
    phone_number = PhoneNumberField(null=True, blank=True)
    balance = models.IntegerField("bal")
    is_anonymous = models.BooleanField()
    is_disabled = models.BooleanField(default=False)
    photo_url = CustomURLField(default="", blank=True)

    stripe_customer_id = models.CharField(max_length=255, default="", blank=True)
    is_paying = models.BooleanField("paid", default=False)

    created_at = models.DateTimeField(
        "created", editable=False, blank=True, default=timezone.now
    )
    upgraded_from_anonymous_at = models.DateTimeField(null=True, blank=True)

    disable_safety_checker = models.BooleanField(default=False)

    objects = AppUserQuerySet.as_manager()

    def __str__(self):
        return f"{self.display_name} ({self.email or self.phone_number or self.uid})"

    def first_name(self):
        if not self.display_name:
            return ""
        return self.display_name.split(" ")[0]

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
        user: AppUser = AppUser.objects.select_for_update().get(pk=self.pk)
        user.balance += amount
        user.save(update_fields=["balance"])
        return AppUserTransaction.objects.create(
            user=self,
            invoice_id=invoice_id,
            amount=amount,
            end_balance=user.balance,
            **kwargs,
        )

    def copy_from_firebase_user(self, user: auth.UserRecord) -> "AppUser":
        # copy data from firebase user
        self.uid = user.uid
        self.is_disabled = user.disabled
        self.display_name = user.display_name or ""
        self.email = user.email
        self.phone_number = user.phone_number
        provider_list = user.provider_data
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
        default_balance = settings.LOGIN_USER_FREE_CREDITS
        if self.is_anonymous:
            default_balance = settings.ANON_USER_FREE_CREDITS
        elif provider_list[-1].provider_id == "password":
            default_balance = settings.EMAIL_USER_FREE_CREDITS
        self.balance = db.get_doc_field(
            doc_ref=db.get_user_doc_ref(user.uid),
            field=db.USER_BALANCE_FIELD,
            default=default_balance,
        )

        return self

    def get_or_create_stripe_customer(self) -> stripe.Customer:
        customer = self.search_stripe_customer()
        if not customer:
            customer = stripe.Customer.create(
                name=self.display_name,
                email=self.email,
                phone=self.phone_number,
                metadata={"uid": self.uid, "id": self.id},
            )
            self.stripe_customer_id = customer.id
            self.save()
        return customer

    def search_stripe_customer(self) -> stripe.Customer | None:
        if not self.uid:
            return None
        if self.stripe_customer_id:
            return stripe.Customer.retrieve(self.stripe_customer_id)
        try:
            customer = stripe.Customer.search(
                query=f'metadata["uid"]:"{self.uid}"'
            ).data[0]
        except IndexError:
            return None
        else:
            self.stripe_customer_id = customer.id
            self.save()
            return customer


class PaymentProvider(models.IntegerChoices):
    STRIPE = 1, "Stripe"
    PAYPAL = 2, "Paypal"


class AppUserTransaction(models.Model):
    user = models.ForeignKey(
        "AppUser", on_delete=models.CASCADE, related_name="transactions"
    )
    invoice_id = models.CharField(max_length=255, unique=True)
    amount = models.IntegerField()
    end_balance = models.IntegerField()
    created_at = models.DateTimeField(editable=False, blank=True, default=timezone.now)
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

    class Meta:
        verbose_name = "Transaction"

    def __str__(self):
        return f"{self.invoice_id} ({self.amount})"
