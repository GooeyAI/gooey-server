import os

from celery import Celery
from celery.schedules import crontab
from daras_ai_v2 import settings


# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "daras_ai_v2.settings")

app = Celery()

app.conf.update(
    broker_url=settings.LOCAL_CELERY_BROKER_URL,
    result_backend=settings.LOCAL_CELERY_RESULT_BACKEND,
    imports=["celeryapp.tasks"],
    task_track_started=True,
    task_acks_late=True,
    task_serializer="pickle",
    accept_content=["pickle"],
    result_serializer="pickle",
    timezone=settings.TIME_ZONE,
    beat_schedule={
        "run_all_scheduled_runs": {
            "task": "bots.tasks.run_all_scheduled_runs",
            "schedule": crontab(hour="0", minute="0"),  # everyday at 00:00
        },
    },
)

# Load task modules from all registered Django apps.
app.autodiscover_tasks()
