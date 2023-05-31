import typing
from functools import wraps

from django.db import reset_queries, close_old_connections

F = typing.TypeVar("F", bound=typing.Callable[..., typing.Any])


def bg_db_task(fn: F) -> F:
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
