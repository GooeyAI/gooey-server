from __future__ import annotations

import typing
from contextlib import contextmanager

from django.http import HttpRequest
from django.http.request import HttpHeaders
import fastapi

F = typing.TypeVar("F", bound=typing.Callable[..., typing.Any])


@contextmanager
def silk_collect(fn: F, args: tuple, kwargs: dict, request: fastapi.Request | None):
    if not silk_enabled():
        yield
        return

    if request:
        path = request.url.path
        query_string = request.url.query
        headers = dict(request.headers)
    else:
        path = f"{fn.__module__}.{fn.__qualname__}"
        query_string = ""
        headers = {}
    body = ", ".join(
        [str(arg) for arg in args] + [f"{k}={v}" for k, v in kwargs.items()]
    ).encode()

    django_request = django_request_for_call(path, query_string, headers, body)
    silk_request = start_silk_collection(django_request)

    try:
        from silk.profiling.profiler import silk_profile

        with silk_profile(name=path):
            yield
    finally:
        finish_silk_collection(silk_request)


def silk_enabled() -> bool:
    from django.conf import settings

    return settings.DEBUG and "silk" in settings.INSTALLED_APPS


def django_request_for_call(
    path: str, query_string: str, headers: dict, body: bytes
) -> HttpRequest:
    django_request = HttpRequest()
    django_request.method = "CALL"
    django_request.path = path
    django_request.path_info = path
    django_request.META = {
        "REQUEST_METHOD": django_request.method,
        "PATH_INFO": path,
        "QUERY_STRING": query_string,
    }
    for name, value in headers.items():
        django_request.META[HttpHeaders.to_wsgi_name(name)] = value
    django_request._body = body
    return django_request


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
