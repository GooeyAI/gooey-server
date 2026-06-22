from __future__ import annotations

import typing
from contextlib import contextmanager
from urllib.parse import urlencode

F = typing.TypeVar("F", bound=typing.Callable[..., typing.Any])


@contextmanager
def silk_collect(fn: F, args: tuple[typing.Any, ...], kwargs: dict[str, typing.Any]):
    if not silk_enabled():
        yield
        return

    django_request = django_request_for_call(fn, args, kwargs)
    silk_request = start_silk_collection(django_request)
    profile_name = f"{fn.__module__}.{fn.__qualname__}"
    try:
        from silk.profiling.profiler import silk_profile

        with silk_profile(name=profile_name):
            yield
    finally:
        finish_silk_collection(silk_request)


def silk_enabled() -> bool:
    from django.conf import settings

    return settings.DEBUG and "silk" in settings.INSTALLED_APPS


def django_request_for_call(
    fn: typing.Callable[..., typing.Any],
    args: tuple[typing.Any, ...],
    kwargs: dict[str, typing.Any],
):
    from django.http import HttpRequest

    path = f"{fn.__module__}.{fn.__qualname__}"
    query_string = _format_call_args(args, kwargs)

    django_request = HttpRequest()
    django_request.method = "CALL"
    django_request.path = path
    django_request.path_info = path
    django_request.META = {
        "REQUEST_METHOD": django_request.method,
        "PATH_INFO": path,
        "CONTENT_TYPE": "",
        "QUERY_STRING": query_string,
    }
    # Silk reads request.body; a bare HttpRequest has no stream/_read_started.
    django_request._body = b""
    return django_request


def _format_call_args(
    args: tuple[typing.Any, ...],
    kwargs: dict[str, typing.Any],
) -> str:
    parts: dict[str, str] = {}
    for index, arg in enumerate(args):
        parts[f"arg{index}"] = _arg_repr(arg)
    for key, value in kwargs.items():
        parts[key] = _arg_repr(value)
    return urlencode(parts)


def _arg_repr(value: typing.Any, *, max_len: int = 120) -> str:
    text = repr(value)
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def start_silk_collection(django_request):
    from django.db.models.sql.compiler import SQLCompiler
    from silk.collector import DataCollector
    from silk.config import SilkyConfig
    from silk.model_factory import RequestModelFactory
    from silk.sql import execute_sql

    DataCollector().clear()
    if not hasattr(SQLCompiler, "_execute_sql"):
        SQLCompiler._execute_sql = SQLCompiler.execute_sql
        SQLCompiler.execute_sql = execute_sql

    request_model = RequestModelFactory(django_request).construct_request_model()
    should_profile = SilkyConfig().SILKY_PYTHON_PROFILER
    DataCollector().configure(request_model, should_profile=should_profile)
    return request_model


def finish_silk_collection(silk_request):
    from django.http import HttpResponse
    from django.utils import timezone
    from silk.collector import DataCollector
    from silk.model_factory import ResponseModelFactory

    collector = DataCollector()
    collector.stop_python_profiler()
    ResponseModelFactory(HttpResponse(status=200)).construct_response_model()
    silk_request.end_time = timezone.now()
    collector.finalise()
    silk_request.save()
