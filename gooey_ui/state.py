import hashlib
import inspect
import threading
import typing
import urllib.parse
from functools import wraps, partial

from fastapi import Depends
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import Response, RedirectResponse, JSONResponse

from gooey_ui.pubsub import (
    get_subscriptions,
    realtime_clear_subs,
)

threadlocal = threading.local()

session_state: dict[str, typing.Any]


def __getattr__(name):
    if name == "session_state":
        return get_session_state()
    else:
        raise AttributeError(name)


def get_query_params() -> dict[str, str]:
    try:
        return threadlocal.query_params
    except AttributeError:
        threadlocal.query_params = {}
        return threadlocal.query_params


def set_query_params(params: dict[str, str]):
    threadlocal.query_params = params


def get_session_state() -> dict[str, typing.Any]:
    try:
        return threadlocal.session_state
    except AttributeError:
        threadlocal.session_state = {}
        return threadlocal.session_state


def set_session_state(state: dict[str, typing.Any]):
    threadlocal.session_state = state


F = typing.TypeVar("F", bound=typing.Callable[..., typing.Any])


def cache_in_session_state(fn: F = None, key="__cache__") -> F:
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # hash the args and kwargs so they are not too long
            args_hash = hashlib.sha256(f"{args}{kwargs}".encode()).hexdigest()
            # create a readable cache key
            cache_key = fn.__name__ + ":" + args_hash
            state = get_session_state()
            try:
                # if the cache exists, return it
                result = state[key][cache_key]
            except KeyError:
                # otherwise, run the function and cache the result
                result = fn(*args, **kwargs)
                state.setdefault(key, {})[cache_key] = result
            return result

        return wrapper

    if fn:
        return decorator(fn)
    else:
        return decorator


Style = dict[str, str | None]
ReactHTMLProps = dict[str, typing.Any]


class RenderTreeNode(BaseModel):
    name: str
    props: ReactHTMLProps = {}
    children: list["RenderTreeNode"] = []

    def mount(self) -> "RenderTreeNode":
        threadlocal._render_root.children.append(self)
        return self


class NestingCtx:
    def __init__(self, node: RenderTreeNode = None):
        self.node = node or threadlocal._render_root
        self.parent = None

    def __enter__(self):
        try:
            self.parent = threadlocal._render_root
        except AttributeError:
            pass
        threadlocal._render_root = self.node

    def __exit__(self, exc_type, exc_val, exc_tb):
        threadlocal._render_root = self.parent

    def empty(self):
        """Empty the children of the node"""
        self.node.children = []
        return self


class RedirectException(Exception):
    def __init__(self, url, status_code=302):
        self.url = url
        self.status_code = status_code


class QueryParamsRedirectException(RedirectException):
    def __init__(self, query_params: dict, status_code=303):
        query_params = {k: v for k, v in query_params.items() if v is not None}
        url = "?" + urllib.parse.urlencode(query_params)
        super().__init__(url, status_code)


def route(app, *paths, **kwargs):
    def decorator(fn):
        @wraps(fn)
        def wrapper(request: Request, json_data: dict | None, **kwargs):
            if "request" in fn_sig.parameters:
                kwargs["request"] = request
            if "json_data" in fn_sig.parameters:
                kwargs["json_data"] = json_data
            return renderer(
                partial(fn, **kwargs),
                query_params=dict(request.query_params),
                state=json_data and json_data.get("state"),
            )

        fn_sig = inspect.signature(fn)
        mod_params = dict(fn_sig.parameters) | dict(
            request=inspect.Parameter(
                "request",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=Request,
            ),
            json_data=inspect.Parameter(
                "json_data",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=Depends(_request_json),
                annotation=typing.Optional[dict],
            ),
        )
        mod_sig = fn_sig.replace(parameters=list(mod_params.values()))
        wrapper.__signature__ = mod_sig

        for path in reversed(paths):
            wrapper = app.get(path)(wrapper)
            wrapper = app.post(path)(wrapper)

        return wrapper

    return decorator


def renderer(
    fn: typing.Callable,
    state: dict[str, typing.Any] = None,
    query_params: dict[str, str] = None,
) -> dict | Response:
    set_session_state(state or {})
    set_query_params(query_params or {})
    realtime_clear_subs()
    while True:
        try:
            root = RenderTreeNode(name="root")
            try:
                with NestingCtx(root):
                    ret = fn()
            except StopException:
                ret = None
            except RedirectException as e:
                return RedirectResponse(e.url, status_code=e.status_code)
            if isinstance(ret, Response):
                return ret
            return JSONResponse(
                jsonable_encoder(
                    dict(
                        children=root.children,
                        state=get_session_state(),
                        channels=get_subscriptions(),
                        **(ret or {}),
                    )
                ),
                headers={"X-GOOEY-GUI-ROUTE": "1"},
            )
        except RerunException:
            continue


async def _request_json(request: Request) -> dict | None:
    if request.headers.get("content-type") == "application/json":
        return await request.json()


def experimental_rerun():
    raise RerunException()


def stop():
    raise StopException()


class StopException(Exception):
    pass


class RerunException(Exception):
    pass


class UploadedFile:
    pass
