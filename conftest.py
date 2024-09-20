import queue
import typing
from collections import defaultdict
from contextlib import contextmanager
from functools import wraps
from threading import Thread
from unittest.mock import patch

import pytest

from auth import auth_backend
from celeryapp import app
from daras_ai_v2.base import BasePage
from daras_ai_v2.send_email import pytest_outbox


def flaky(fn):
    max_tries = 5

    @wraps(fn)
    def wrapper(*args, **kwargs):
        for i in range(max_tries):
            try:
                return fn(*args, **kwargs)
            except Exception:
                if i == max_tries - 1:
                    raise

    return wrapper


@pytest.fixture
def db_fixtures(transactional_db):
    from django.core.management import call_command

    print("Loading fixtures from fixture.json")
    call_command("loaddata", "fixture.json")


@pytest.fixture
def force_authentication():
    with auth_backend.force_authentication() as user:
        yield user


app.conf.task_always_eager = True

redis_qs = defaultdict(queue.Queue)


@pytest.fixture
def mock_celery_tasks():
    with (
        patch("celeryapp.tasks.runner_task", _mock_runner_task),
        patch("celeryapp.tasks.post_runner_tasks", _mock_post_runner_tasks),
        patch("gooey_gui.realtime_subscribe", _mock_realtime_subscribe),
    ):
        yield


@app.task
def _mock_runner_task(
    *, page_cls: typing.Type[BasePage], run_id: str, uid: str, **kwargs
):
    sr = page_cls.get_sr_from_ids(run_id, uid)
    sr.set(sr.parent.to_dict())
    sr.save()
    channel = page_cls.realtime_channel_name(run_id, uid)
    _mock_realtime_push(channel, sr.to_dict())


@app.task
def _mock_post_runner_tasks(*args, **kwargs):
    pass


def _mock_realtime_push(channel, value):
    redis_qs[channel].put(value)


@contextmanager
def _mock_realtime_subscribe(channel: str):
    def iterq():
        while True:
            yield redis_qs[channel].get()

    yield iterq()


@pytest.fixture
def threadpool_subtest(subtests, max_workers: int = 128):
    ts = []

    def submit(fn, *args, msg=None, **kwargs):
        if not msg:
            msg = "--".join(map(str, [*args, *kwargs.values()]))

        @wraps(fn)
        def runner(*args, **kwargs):
            with subtests.test(msg=msg):
                return fn(*args, **kwargs)

        ts.append(Thread(target=runner, args=args, kwargs=kwargs))

    yield submit

    for i in range(0, len(ts), max_workers):
        s = slice(i, i + max_workers)
        for t in ts[s]:
            t.start()
        for t in ts[s]:
            t.join()


@pytest.fixture(autouse=True)
def clear_pytest_outbox():
    pytest_outbox.clear()
