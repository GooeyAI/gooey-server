import shlex
import subprocess
import sys

from django.utils import autoreload


def restart_celery(celery_args):
    celery_base_cmd = "celery -A celeryapp worker"
    subprocess.call(["pkill", "-f", celery_base_cmd])
    cmd = ["poetry", "run"] + shlex.split(celery_base_cmd) + shlex.split(celery_args)
    print("Running command: ", cmd, file=sys.stderr)
    subprocess.call(cmd)


def run(celery_args=""):
    print("Starting celery worker with autoreload...", file=sys.stderr)

    autoreload.run_with_reloader(lambda: restart_celery(celery_args))
