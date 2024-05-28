import os.path
import typing
from urllib.parse import parse_qs

from fastapi import Depends
from fastapi.routing import APIRoute
from furl import furl
from starlette.requests import Request


async def request_json(request: Request):
    return await request.json()


async def request_urlencoded_body(request: Request):
    body = await request.body()
    return parse_qs(body.decode())


async def request_form(request: Request):
    return await request.form()


async def request_body(request: Request):
    return await request.body()


fastapi_request_json = Depends(request_json)
fastapi_request_urlencoded_body = Depends(request_urlencoded_body)
fastapi_request_form = Depends(request_form)
fastapi_request_body = Depends(request_body)


class ResolverMatch(typing.NamedTuple):
    route: APIRoute
    matched_params: dict


def resolve_url(url: str) -> ResolverMatch | None:
    from server import app

    path = os.path.join(furl(url).pathstr, "")
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        match = route.path_regex.match(path)
        if not match:
            continue
        matched_params = match.groupdict()
        for key, value in matched_params.items():
            matched_params[key] = route.param_convertors[key].convert(value)
        return ResolverMatch(route=route, matched_params=matched_params)

    return None


def get_route_url(route_fn: typing.Callable, params: dict = None):
    from server import app

    return os.path.join(app.url_path_for(route_fn.__name__, **(params or {})), "")
