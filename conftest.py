import queue
import typing
from collections import defaultdict
from contextlib import contextmanager
from functools import wraps
from threading import Thread
from unittest.mock import patch

import pytest
from pytest_subtests import subtests

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


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
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
def mock_gui_runner():
    with (
        patch("celeryapp.tasks.gui_runner", _mock_gui_runner),
        patch("daras_ai_v2.bots.realtime_subscribe", _mock_realtime_subscribe),
    ):
        yield


@app.task
def _mock_gui_runner(
    *, page_cls: typing.Type[BasePage], run_id: str, uid: str, **kwargs
):
    sr = page_cls.run_doc_sr(run_id, uid)
    sr.set(sr.parent.to_dict())
    sr.save()
    channel = page_cls().realtime_channel_name(run_id, uid)
    _mock_realtime_push(channel, sr.to_dict())


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


# class DummyDatabaseBlocker(pytest_django.plugin._DatabaseBlocker):
#     class _dj_db_wrapper:
#         def ensure_connection(self):
#             pass
#
#
# @pytest.mark.tryfirst
# def pytest_sessionstart(session):
#     # make the session threadsafe
#     _pytest.runner.SetupState = ThreadLocalSetupState
#
#     # ensure that the fixtures (specifically finalizers) are threadsafe
#     _pytest.fixtures.FixtureDef = ThreadLocalFixtureDef
#
#     django.test.utils._TestState = threading.local()
#
#     # make the environment threadsafe
#     os.environ = ThreadLocalEnviron(os.environ)
#
#
# @pytest.hookimpl
# def pytest_runtestloop(session: _pytest.main.Session):
#     if session.testsfailed and not session.config.option.continue_on_collection_errors:
#         raise session.Interrupted(
#             "%d error%s during collection"
#             % (session.testsfailed, "s" if session.testsfailed != 1 else "")
#         )
#
#     if session.config.option.collectonly:
#         return True
#
#     num_threads = 10
#
#     threadpool_items = [
#         item
#         for item in session.items
#         if any("run_in_threadpool" in marker.name for marker in item.iter_markers())
#     ]
#
#     manager = pytest_django.plugin._blocking_manager
#     pytest_django.plugin._blocking_manager = DummyDatabaseBlocker()
#     try:
#         with manager.unblock():
#             for j in range(0, len(threadpool_items), num_threads):
#                 s = slice(j, j + num_threads)
#                 futs = []
#                 for i, item in enumerate(threadpool_items[s]):
#                     nextitem = (
#                         threadpool_items[i + 1]
#                         if i + 1 < len(threadpool_items)
#                         else None
#                     )
#                     p = threading.Thread(
#                         target=item.config.hook.pytest_runtest_protocol,
#                         kwargs=dict(item=item, nextitem=nextitem),
#                     )
#                     p.start()
#                     futs.append(p)
#                 for p in futs:
#                     p.join()
#                     if session.shouldfail:
#                         raise session.Failed(session.shouldfail)
#                     if session.shouldstop:
#                         raise session.Interrupted(session.shouldstop)
#     finally:
#         pytest_django.plugin._blocking_manager = manager
#
#     session.items = [
#         item
#         for item in session.items
#         if not any("run_in_threadpool" in marker.name for marker in item.iter_markers())
#     ]
#     for i, item in enumerate(session.items):
#         nextitem = session.items[i + 1] if i + 1 < len(session.items) else None
#         item.config.hook.pytest_runtest_protocol(item=item, nextitem=nextitem)
#         if session.shouldfail:
#             raise session.Failed(session.shouldfail)
#         if session.shouldstop:
#             raise session.Interrupted(session.shouldstop)
#     return True
