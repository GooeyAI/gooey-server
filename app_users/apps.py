from django.apps import AppConfig


class AppUsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "app_users"

    def ready(self):
        from . import signals

        assert signals
