from django.db.models.signals import post_delete
from django.dispatch import receiver

from daras_ai_v2.glossary import delete_glossary
from glossary_resources.models import GlossaryResource


@receiver(post_delete, sender=GlossaryResource)
def on_glossary_resource_deleted(instance: GlossaryResource, **kwargs):
    delete_glossary(
        project_id=instance.project_id,
        location=instance.location,
        glossary_name=instance.glossary_name,
    )
