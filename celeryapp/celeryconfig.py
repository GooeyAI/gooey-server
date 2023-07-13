import os

from celery import Celery
from daras_ai_v2 import settings


# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "daras_ai_v2.settings")

app = Celery()

app.conf.update(
    broker_url=settings.LOCAL_CELERY_BROKER_URL,
    imports=["celeryapp.tasks"],
    task_track_started=True,
    task_acks_late=True,
    task_serializer="pickle",
    accept_content=["pickle"],
)

# Load task modules from all registered Django apps.
app.autodiscover_tasks()
