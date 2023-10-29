from django.apps import AppConfig


class GlossaryResourcesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "glossary_resources"
    verbose_name = "Glossary Resources"

    def ready(self):
        import glossary_resources.signals

        assert glossary_resources.signals
