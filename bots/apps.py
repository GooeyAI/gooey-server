from django.apps import AppConfig


class MessagesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "bots"

    def ready(self):
        import bots.signals
