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
        indexes = [
            models.Index(
                fields=[
                    "useage_count",
                    "last_updated",
                ]
            ),
        ]

    def __str__(self):
        return f"{self.f_url} ({self.useage_count} uses)"

    def get_clean_name(self):
        return str(self.glossary_name).lower()
