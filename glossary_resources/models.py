from django.db import models
from bots.custom_fields import CustomURLField
import uuid


class GlossaryResource(models.Model):
    f_url = CustomURLField(unique=True)
    useage_count = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)
    glossary_name = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)

    class Meta:
        ordering = ["useage_count", "last_updated"]

    def get_clean_name(self):
        return str(self.glossary_name).lower()
