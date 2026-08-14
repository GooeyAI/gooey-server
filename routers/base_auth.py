from __future__ import annotations

import typing
from urllib.parse import urlparse

import fastapi
from django.utils.http import url_has_allowed_host_and_scheme
from furl import furl

from daras_ai_v2 import settings
from routers.custom_api_router import CustomAPIRouter

if typing.TYPE_CHECKING:
    from daras_ai_v2.base import BasePageRequest

app = CustomAPIRouter()

DEFAULT_LOGIN_REDIRECT = "/explore/"
DEFAULT_LOGOUT_REDIRECT = "/"


@app.get("/logout/")
async def logout(request: fastapi.Request):
    request.session.clear()
    # Return a small page that clears leftover Google / Firebase client state
    # before navigating away. A 302 alone cannot touch sessionStorage, and
    # stale GSI / FirebaseUI redirect state is what produces Google's
    # accounts.google.com 400 after the next Sign in with Google click.
    response = settings.templates.TemplateResponse(
        "logout.html",
        context={
            "request": request,
            "next_url": safe_next_url(
                request.query_params, default=DEFAULT_LOGOUT_REDIRECT
            ),
        },
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def get_login_url(
    request: fastapi.Request | BasePageRequest, next_url: str | None = None
) -> str:
    next_url = str(furl(next_url or request.url).set(origin=None))
    return str(furl("/login/", query_params=dict(next=next_url)))


def safe_next_url(query_params, *, default: str, redirect_param: str = "next") -> str:
    redirect_to = query_params.get(redirect_param)
    if redirect_to and url_has_allowed_host_and_scheme(
        redirect_to, allowed_hosts=_redirect_allowed_hosts()
    ):
        return redirect_to
    else:
        return default


def _redirect_allowed_hosts() -> set[str]:
    return {host for url in SAFE_URLS if (host := urlparse(url).netloc)}


SAFE_URLS = (
    settings.APP_BASE_URL,
    settings.API_BASE_URL,
    settings.ADMIN_BASE_URL,
)
