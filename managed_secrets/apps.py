from django.apps import AppConfig


class ManagedSecretsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "managed_secrets"

    def ready(self):
        from . import signals

        assert signals
