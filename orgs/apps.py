from django.apps import AppConfig


class OrgsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "orgs"

    def ready(self):
        from . import signals

        assert signals
