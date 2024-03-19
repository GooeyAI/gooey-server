import typing
from functools import wraps

from django.db import reset_queries, close_old_connections

if typing.TYPE_CHECKING:
    import celery.result

F = typing.TypeVar("F", bound=typing.Callable[..., typing.Any])


def db_middleware(fn: F) -> F:
    """
    Decorator to ensure the `fn` runs safely in a background task with a new database connection.
    Workaround for https://code.djangoproject.com/ticket/24810
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        reset_queries()
        close_old_connections()
        try:
            return fn(*args, **kwargs)
        finally:
            close_old_connections()

    return wrapper


next_db_safe = db_middleware(next)


@db_middleware
def get_celery_result_db_safe(
    result: "celery.result.AsyncResult", **kwargs
) -> typing.Any:
    return result.get(disable_sync_subtasks=False, **kwargs)
