from __future__ import annotations

import itertools
import re
import typing

from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator, RegexValidator
from django.db import IntegrityError, models
from django.db.models.functions import Upper
from furl import furl

from bots.custom_fields import CustomURLField
from daras_ai_v2 import settings

if typing.TYPE_CHECKING:
    from app_users.models import AppUser
    from workspaces.models import Workspace


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
    "sales",
    "js",
    "css",
    "assets",
    "favicon.ico",
]
COMMON_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "outlook.com",
    "hotmail.com",
    "yahoo.com",
    "myyahoo.com",
    "proton.me",
    "protonmail.com",
    "aol.com",
    "aim.com",
    "icloud.com",
    "yandex.com",
    "tutanota.com",
    "tuta.com",
    "tutanota.de",
    "tutamail.com",
    "tuta.io",
    "keemail.me",
    "zohomail.com",
}
PRIVATE_EMAIL_DOMAINS = [
    "privaterelay.appleid.com",
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

    def _validate_exclusive(self):
        lookups = [self.has_redirect, self.has_workspace]
        if sum(lookups) > 1:
            raise ValidationError("A handle must be exclusive")

    def clean(self):
        self._validate_exclusive()
        super().clean()

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def has_workspace(self):
        try:
            self.workspace
        except Handle.workspace.RelatedObjectDoesNotExist:
            return False
        else:
            return True

    @property
    def has_redirect(self):
        return bool(self.redirect_url)

    @classmethod
    def create_default_for_workspace(cls, workspace: "Workspace"):
        for handle_name in _generate_handle_options(workspace):
            if handle := _attempt_create_handle(handle_name):
                return handle
        return None

    @classmethod
    def get_suggestion_for_team_workspace(cls, display_name: str) -> str | None:
        options_generator = _generate_handle_options_for_team_workspace(display_name)
        while options_generator:
            options = list(itertools.islice(options_generator, 10))
            existing_handles = set(
                cls.objects.filter(name__in=options).values_list("name", flat=True)
            )
            for option in options:
                if option not in existing_handles:
                    return option

    def get_app_url(self):
        return str(furl(settings.APP_BASE_URL) / self.name / "/")


def _make_handle_from(name):
    allowed_groups = [m for m in re.findall(HANDLE_ALLOWED_CHARS, name)]
    if len(allowed_groups) == 1:
        # as it is
        name = allowed_groups[0]
    else:
        # capitalize first letter of each valid group
        name = "".join(capitalize_first(group) for group in allowed_groups)

    name = name[:HANDLE_MAX_LENGTH]
    name = name.rstrip("-_.")
    return name


def _generate_handle_options(workspace: "Workspace") -> typing.Iterator[str]:
    if workspace.is_personal:
        yield from _generate_handle_options_for_personal_workspace(workspace.created_by)
    else:
        yield from _generate_handle_options_for_team_workspace(
            display_name=workspace.display_name()
        )


def _generate_handle_options_for_personal_workspace(
    user: "AppUser",
) -> typing.Iterator[str]:
    if user.is_anonymous or not user.email:
        return

    email_domain = user.email.split("@")[-1]

    if email_domain in COMMON_EMAIL_DOMAINS:
        # popular mail provider where user set their own email prefix
        email_prefix = _make_handle_from(user.email.split("@")[0])
        if email_prefix:
            yield email_prefix

        if user.display_name:
            name_handle = _make_handle_from(user.display_name)
            yield name_handle
            for i in range(1, 10):
                yield f"{name_handle[:HANDLE_MAX_LENGTH-1]}{i}"

    elif email_domain in PRIVATE_EMAIL_DOMAINS:
        # prefix is not useful
        if user.display_name:
            name_handle = _make_handle_from(user.display_name)
            yield name_handle
            for i in range(1, 10):
                yield f"{name_handle[:HANDLE_MAX_LENGTH-1]}{i}"

    else:
        # probably an org email
        if user.display_name:
            yield _make_handle_from(user.display_name)

        email_prefix = user.email.split("@")[0]
        domain_part = email_domain.split(".")[0]
        email_handle = _make_handle_from(
            capitalize_first(email_prefix) + capitalize_first(domain_part)
        )

        yield email_handle
        for i in range(1, 10):
            yield f"{email_handle[:HANDLE_MAX_LENGTH-1]}{i}"


def _generate_handle_options_for_team_workspace(
    display_name: str,
) -> typing.Iterator[str]:
    handle_name = _make_handle_from(display_name)
    yield handle_name[:HANDLE_MAX_LENGTH]
    for i in range(1, 10):
        yield f"{handle_name[:HANDLE_MAX_LENGTH-1]}{i}"


def _attempt_create_handle(handle_name: str):
    handle = Handle(name=handle_name)
    try:
        handle.full_clean()
        handle.save()
        return handle
    except (IntegrityError, ValidationError):
        return None


def capitalize_first(s: str) -> str:
    return s[0].upper() + s[1:] if s else ""
