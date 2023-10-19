from django.db import models
from bots.custom_fields import CustomURLField
import uuid


class GlossaryResource(models.Model):
    f_url = CustomURLField(unique=True)
    usage_count = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)
    glossary_name = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    project_id = models.CharField(max_length=100, default="dara-c1b52")
    location = models.CharField(max_length=100, default="us-central1")

    class Meta:
        ordering = ["usage_count", "last_updated"]
        indexes = [
            models.Index(
                fields=[
                    "usage_count",
                    "last_updated",
                ]
            ),
        ]

    def __str__(self):
        return f"{self.f_url} ({self.usage_count} uses)"

    def get_clean_name(self):
        return "glossary-" + str(self.glossary_name).lower()
