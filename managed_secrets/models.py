import uuid

from daras_ai_v2 import settings
from django.db import models

'az role assignment create --role "Key Vault Secrets Officer" --assignee "<upn>" --scope "/subscriptions/<subscription-id>/resourceGroups/<resource-group-name>/providers/Microsoft.KeyVault/vaults/<your-unique-keyvault-name>"'


class ManagedSecretQuerySet(models.QuerySet):
    def create(self, *, value: str, **kwargs):
        secret = super().create(**kwargs)
        secret.value = value
        return secret


class ManagedSecret(models.Model):
    external_id = models.UUIDField(default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=255)

    workspace = models.ForeignKey(
        "workspaces.Workspace", on_delete=models.CASCADE, related_name="managed_secrets"
    )
    created_by = models.ForeignKey(
        "app_users.AppUser", on_delete=models.SET_NULL, null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    usage_count = models.PositiveIntegerField(default=0, db_index=True)
    last_used_at = models.DateTimeField(null=True, blank=True, default=None)

    objects: ManagedSecretQuerySet = ManagedSecretQuerySet.as_manager()

    class Meta:
        unique_together = ("workspace", "name")

    def __str__(self):
        return f"{self.name} ({self._external_name()})"

    _value: str | None = None

    class NotFoundError(Exception):
        pass

    @property
    def value(self) -> str:
        if self._value is None:
            raise self.NotFoundError()
        return self._value

    @value.setter
    def value(self, x: str):
        self.store_value(x)

    def store_value(self, value: str):
        client = _get_az_secret_client()
        client.set_secret(self._external_name(), value)
        self._value = value

    def load_value(self):
        import azure.core.exceptions

        client = _get_az_secret_client()
        try:
            self._value = client.get_secret(self._external_name()).value
        except azure.core.exceptions.ResourceNotFoundError:
            self._value = None

    def delete_value(self):
        import azure.core.exceptions

        client = _get_az_secret_client()
        try:
            client.begin_delete_secret(self._external_name())
        except azure.core.exceptions.ResourceNotFoundError:
            pass

    def _external_name(self):
        return f"ms-gooey-{self.external_id}"


def _get_az_secret_client():
    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient

    credential = DefaultAzureCredential()
    return SecretClient(
        vault_url=settings.AZURE_KEY_VAULT_ENDPOINT, credential=credential
    )
