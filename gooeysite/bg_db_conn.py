import typing
from functools import wraps

from django.db import reset_queries, close_old_connections

from gooeysite.silkify import silk_collect

if typing.TYPE_CHECKING:
    import celery.result

F = typing.TypeVar("F", bound=typing.Callable[..., typing.Any])


def db_middleware(fn: F) -> F:
    """
    Decorator to ensure the `fn` runs safely in a background task with a new database connection.
    Workaround for https://code.djangoproject.com/ticket/24810
    """
    if getattr(fn, "__db_middleware__", False):
        return fn

    @wraps(fn)
    def wrapper(*args, **kwargs):
        reset_queries()
        close_old_connections()
        try:
            with silk_collect(fn, args, kwargs):
                return fn(*args, **kwargs)
        finally:
            close_old_connections()

    wrapper.__db_middleware__ = True
    return wrapper


@db_middleware
def get_celery_result_db_safe(
    result: "celery.result.AsyncResult", **kwargs
) -> typing.Any:
    return result.get(disable_sync_subtasks=False, **kwargs)
