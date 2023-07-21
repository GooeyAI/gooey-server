import datetime

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

    display_name = models.TextField(default="", blank=True)
    email = models.EmailField(null=True, blank=True)
    phone_number = PhoneNumberField(null=True, blank=True)
    balance = models.IntegerField()
    is_anonymous = models.BooleanField()
    is_disabled = models.BooleanField(default=False)
    photo_url = CustomURLField(default="", blank=True)

    stripe_customer_id = models.CharField(max_length=255, default="", blank=True)

    created_at = models.DateTimeField(editable=False, blank=True, default=timezone.now)
    upgraded_from_anonymous_at = models.DateTimeField(null=True, blank=True)

    objects = AppUserQuerySet.as_manager()

    def __str__(self):
        return f"{self.display_name} ({self.email or self.phone_number or self.uid})"

    def first_name(self):
        if not self.display_name:
            return ""
        return self.display_name.split(" ")[0]

    def add_balance(self, amount: int, invoice_id: str, **invoice_items):
        from google.cloud import firestore
        from google.cloud.firestore_v1.transaction import Transaction

        @firestore.transactional
        @db_middleware
        def _update_user_balance_in_txn(txn: Transaction):
            user_doc_ref = db.get_user_doc_ref(self.uid)

            invoice_ref: firestore.DocumentReference
            invoice_ref = user_doc_ref.collection("invoices").document(invoice_id)
            # if an invoice entry exists
            if invoice_ref.get(transaction=txn).exists:
                # avoid updating twice for same invoice
                return

            obj = self.add_balance_direct(amount)

            # create invoice entry
            txn.create(
                invoice_ref,
                {
                    "amount": amount,
                    "end_balance": obj.balance,
                    "timestamp": datetime.datetime.utcnow(),
                    **invoice_items,
                },
            )

        _update_user_balance_in_txn(db.get_client().transaction())

    @transaction.atomic
    def add_balance_direct(self, amount):
        obj: AppUser = self.__class__.objects.select_for_update().get(pk=self.pk)
        obj.balance += amount
        obj.save(update_fields=["balance"])
        return obj

    def copy_from_firebase_user(self, user: auth.UserRecord) -> "AppUser":
        # copy data from firebase user
        self.uid = user.uid
        self.is_disabled = user.disabled
        self.display_name = user.display_name or ""
        self.email = user.email
        self.phone_number = user.phone_number
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
        self.balance = db.get_doc_field(
            doc_ref=db.get_user_doc_ref(user.uid),
            field=db.USER_BALANCE_FIELD,
            default=(
                settings.ANON_USER_FREE_CREDITS
                if self.is_anonymous
                else settings.LOGIN_USER_FREE_CREDITS
            ),
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
