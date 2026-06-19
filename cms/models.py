from django.db import models
from django.utils import timezone

from bots.custom_fields import CustomURLField


class NewsItem(models.Model):
    headline = models.CharField(max_length=200)
    tag = models.CharField(
        max_length=64,
        help_text='Freeform label, e.g. "Event", "Product", "Case Study".',
    )
    photo_url = CustomURLField(default="", blank=True)
    publish_date = models.DateTimeField(default=timezone.now)
    url = CustomURLField(default="", blank=False, help_text="News item URL.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.headline
