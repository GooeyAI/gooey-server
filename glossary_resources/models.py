from django.db import models
from bots.custom_fields import CustomURLField
import uuid


class GlossaryResources(models.Model):
    f_url = CustomURLField(unique=True)
    uses = models.IntegerField(default=0)
    last_used = models.DateTimeField(auto_now=True)
    glossary_name = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)

    class Meta:
        ordering = ["uses", "last_used"]

    def get_clean_name(self):
        return str(self.glossary_name).lower()
