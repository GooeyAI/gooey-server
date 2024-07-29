from django.apps import AppConfig


class StaticPagesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "static_pages"
    verbose_name = "Static Pages"

    def ready(self):
        from . import signals

        return signals
