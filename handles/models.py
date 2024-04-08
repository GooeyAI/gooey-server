from __future__ import annotations

import re
import uuid

from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator, RegexValidator
from django.db import IntegrityError, models
from django.db.models.functions import Upper
from furl import furl

from bots.custom_fields import CustomURLField
from daras_ai_v2 import settings

HANDLE_ALLOWED_CHARS = r"[A-Za-z0-9_\.-]+"
HANDLE_REGEX = rf"^{HANDLE_ALLOWED_CHARS}$"
HANDLE_MAX_LENGTH = 40
BASE_HANDLE_BLACKLIST = [
    "admin",
    "account",
    "login",
    "logout",
    "api",
    "faq",
    "pricing",
    "privacy",
    "terms",
    "team",
    "about",
    "blog",
    "contact",
    "sales",
]

validate_handle_regex = RegexValidator(
    regex=HANDLE_REGEX,
    message="Handles must contain only letters, numbers, and the characters . _ -",
)

validate_handle_length = MaxLengthValidator(
    limit_value=HANDLE_MAX_LENGTH,
    message=f"Handles must be at most {HANDLE_MAX_LENGTH} characters long",
)


def get_handle_blacklist():
    from daras_ai_v2.all_pages import page_slug_map

    return BASE_HANDLE_BLACKLIST + list(page_slug_map.keys())


def validate_handles_blacklist(value):
    from daras_ai_v2.all_pages import normalize_slug

    if normalize_slug(value) in get_handle_blacklist():
        raise ValidationError(f"{value} is a reserved handle")


class HandleQuerySet(models.QuerySet):
    def get_by_name(self, name: str) -> Handle:
        """
        Get a handle by name, case-insensitive
        """
        return self.get(name__iexact=name)


class Handle(models.Model):
    name = models.TextField(
        validators=[
            validate_handle_length,
            validate_handle_regex,
            validate_handles_blacklist,
        ],
    )

    redirect_url = CustomURLField(default=None, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = HandleQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Upper("name"),
                name="handle_upper_name_is_unique",
                violation_error_message="A handle with this name already exists",
            )
        ]

    def __str__(self):
        return f"@{self.name}"

    def clean(self):
        lookups = [
            self.has_redirect,
            self.has_user,
        ]
        if sum(lookups) > 1:
            raise ValidationError("A handle must be exclusive")

        super().clean()

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def has_user(self):
        try:
            self.user
        except Handle.user.RelatedObjectDoesNotExist:
            return False
        else:
            return True

    @property
    def has_redirect(self):
        return bool(self.redirect_url)

    @classmethod
    def create_default_for_user(cls, user: "AppUser"):
        for handle_name in _generate_handle_options(user):
            if handle := _attempt_create_handle(handle_name):
                return handle
        return None

    def get_app_url(self):
        return str(furl(settings.APP_BASE_URL) / self.name / "/")


def _make_handle_from(name):
    name = name.lower()
    name = "".join(
        m.capitalize() for m in re.findall(HANDLE_ALLOWED_CHARS, name)
    )  # find groups of valid chars
    name = name[:HANDLE_MAX_LENGTH]
    name = name.rstrip("-_")
    return name


def _generate_handle_options(user):
    email_handle = _make_handle_from(user.email.split("@")[0]) if user.email else ""
    if email_handle:
        yield email_handle

    if user.display_name:
        yield _make_handle_from(user.display_name)

    if email_handle:
        for i in range(10):
            yield f"{email_handle}{i}"


def _attempt_create_handle(handle_name):
    from handles.models import Handle

    handle = Handle(name=handle_name)
    try:
        handle.full_clean()
        handle.save()
        return handle
    except (IntegrityError, ValidationError):
        return None
