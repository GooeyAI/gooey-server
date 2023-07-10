from gooeysite import wsgi

assert wsgi

from celery import Celery
from daras_ai_v2 import settings


app = Celery()

app.conf.update(
    broker_url=settings.LOCAL_CELERY_BROKER_URL,
    imports=["celeryapp.tasks"],
    task_track_started=True,
    task_acks_late=True,
    task_serializer="pickle",
    accept_content=["pickle"],
)
