import typing
from functools import wraps

from django.db import connections

F = typing.TypeVar("F", bound=typing.Callable[..., typing.Any])


def db_middleware(fn: F) -> F:
    """Decorator to ensure the `fn` runs safely in a background task with a new database connection."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        reset_queries()
        close_old_connections()
        try:
            return fn(*args, **kwargs)
        finally:
            close_old_connections()

    return wrapper


# The below code is stolen from https://github.com/arteria/django-background-tasks/blob/master/background_task/signals.py
#


# Register an event to reset saved queries when a Task is started.
def reset_queries(**kwargs):
    for conn in connections.all():
        conn.queries_log.clear()


# Register an event to reset transaction state and close connections past
# their lifetime.
def close_old_connections(**kwargs):
    for conn in connections.all():
        conn.close_if_unusable_or_obsolete()
