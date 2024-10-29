import typing

from django.db import models
from django.utils import timezone

from daras_ai_v2.crypto import PBKDF2PasswordHasher, get_random_api_key, safe_preview

if typing.TYPE_CHECKING:
    from workspaces.models import Workspace


class ApiKeyQueySet(models.QuerySet):
    def create_api_key(self, workspace: "Workspace", **kwargs) -> tuple["ApiKey", str]:
        """
        Returns a tuple of the created ApiKey instance and the secret key.
        """
        secret_key = get_random_api_key()
        hasher = PBKDF2PasswordHasher()
        api_key = self.create(
            hash=hasher.encode(secret_key),
            preview=safe_preview(secret_key),
            workspace=workspace,
            **kwargs,
        )
        return api_key, secret_key

    def get_from_secret_key(self, secret_key: str) -> "ApiKey":
        hasher = PBKDF2PasswordHasher()
        hash = hasher.encode(secret_key)
        return self.get(hash=hash)


class ApiKey(models.Model):
    hash = models.CharField(max_length=128, unique=True)
    preview = models.CharField(max_length=32)
    workspace = models.ForeignKey(
        "workspaces.Workspace", on_delete=models.CASCADE, related_name="api_keys"
    )
    created_by = models.ForeignKey(
        "app_users.AppUser", on_delete=models.SET_NULL, null=True
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ApiKeyQueySet.as_manager()

    def __str__(self):
        return self.preview

    class Meta:
        verbose_name = "API Key"
        verbose_name_plural = "API Keys"
