from contextlib import contextmanager, nullcontext
import typing
from functools import wraps

import fastapi
from django.db import reset_queries, close_old_connections

from gooeysite.silkify import silk_collect
from daras_ai_v2 import settings
from contextvars import ContextVar

if typing.TYPE_CHECKING:
    import celery.result


F = typing.TypeVar("F", bound=typing.Callable[..., typing.Any])

current_request: ContextVar[fastapi.Request | None] = ContextVar(
    "current_request", default=None
)


def db_middleware(fn: F) -> F:
    """
    Decorator to ensure the `fn` runs safely in a background task with a new database connection.
    Workaround for https://code.djangoproject.com/ticket/24810
    """
    if getattr(fn, "__db_middleware__", False):
        return fn

    @wraps(fn)
    def wrapper(*args, **kwargs):
        if settings.DEBUG:
            silk_ctx = silk_collect(fn, args, kwargs, current_request.get())
        else:
            silk_ctx = nullcontext()
        with db_connection(), silk_ctx:
            return fn(*args, **kwargs)

    wrapper.__db_middleware__ = True
    return wrapper


@contextmanager
def db_connection():
    """
    Context manager to ensure the database connection is reset and closed.
    Workaround for https://code.djangoproject.com/ticket/24810
    """
    reset_queries()
    close_old_connections()
    try:
        yield
    finally:
        close_old_connections()


@db_middleware
def get_celery_result_db_safe(
    result: "celery.result.AsyncResult", **kwargs
) -> typing.Any:
    return result.get(disable_sync_subtasks=False, **kwargs)
