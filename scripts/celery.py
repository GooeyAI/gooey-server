import shlex
import subprocess

from django.utils import autoreload


def restart_celery():
    celery_cmd = "celery -A celeryapp worker -P threads -c 48 -l DEBUG"
    subprocess.call(["pkill", "-f", celery_cmd])
    cmd = f"poetry run {celery_cmd}"
    subprocess.call(shlex.split(cmd))


def run():
    print("Starting celery worker with autoreload...")

    autoreload.run_with_reloader(restart_celery)
