import requests
from django.db import models, IntegrityError, transaction
from django.utils import timezone
from firebase_admin import auth

from bots.custom_fields import CustomURLField
from daras_ai.image_input import upload_file_from_bytes, guess_ext_from_response
from daras_ai_v2 import settings, db
from gooeysite.bg_db_conn import db_middleware


# class CostQuerySet(models.QuerySet):


class Cost(models.Model):
    run_id = models.ForeignKey(
        "bots.SavedRun",
        on_delete=models.SET_NULL,
        related_name="cost",
        null=True,
        default=None,
        blank=True,
        help_text="The run that was last saved by the user.",
    )
    provider = models.CharField(max_length=255, default="", blank=True)
    model = models.TextField("model", blank=True)
    param = models.TextField("param", blank=True)
    notes = models.TextField(default="", blank=True)
    quantity = models.IntegerField(default=1)
    calculation_notes = models.TextField(default="", blank=True)
    cost = models.FloatField(default=0.0)
    input = models.
