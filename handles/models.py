from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import CheckConstraint, Q
from django.db.models.functions import Lower

from bots.custom_fields import CustomURLField


HANDLE_REGEX = r"^[a-z0-9_.-]+$"

HANDLE_BLACKLIST = [
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


def validate_handles_blacklist(value):
    if value.lower() in HANDLE_BLACKLIST:
        raise ValidationError(f"{value} is a reserved handle")


class Handle(models.Model):
    """
    Note: always convert the search name to lowercase when matching with `name`.
    e.g. to find a handle with name `search_value`, use `Handle.objects.get(name=search_value.lower())`.
    """

    name = models.TextField(
        unique=True,
        validators=[
            validate_handle_regex,
            validate_handles_blacklist,
        ],
    )

    redirect_url = CustomURLField(default=None, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"@{self.name}"

    def clean(self):
        lookups = [
            bool(self.redirect_url),
            self.has_user,
        ]
        if sum(lookups) > 1:
            raise ValidationError("A handle must be exclusive")

        super().clean()

    def save(self, *args, **kwargs):
        self.name = self.name.lower()
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

    class Meta:
        constraints = [
            # Ensure that all names are lowercase
            CheckConstraint(
                check=Q(name=Lower("name")),
                name="handle_name_is_lowercase",
                violation_error_message="Handle must be lowercase",
            )
        ]
