import os
import traceback

from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from furl import furl
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.status import (
    HTTP_404_NOT_FOUND,
    HTTP_405_METHOD_NOT_ALLOWED,
)

from daras_ai_v2.pydantic_validation import convert_errors
from daras_ai_v2.settings import templates
from gooeysite import wsgi

assert wsgi

import logging

import anyio
from decouple import config


from time import time

from fastapi.routing import APIRoute
from starlette._utils import is_async_callable

from gooeysite.bg_db_conn import db_middleware

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.middleware.sessions import SessionMiddleware

from auth.auth_backend import (
    SessionAuthBackend,
)
from daras_ai_v2 import settings
from routers import (
    account,
    facebook_api,
    api,
    root,
    slack_api,
    paypal,
    stripe,
    broadcast_api,
    bots_api,
    twilio_api,
    static_pages,
)
import url_shortener.routers as url_shortener

app = FastAPI(title="GOOEY.AI", docs_url=None, redoc_url="/docs")

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(bots_api.app)
app.include_router(api.app)
app.include_router(broadcast_api.app)
app.include_router(account.app, include_in_schema=False)
app.include_router(facebook_api.app, include_in_schema=False)
app.include_router(slack_api.router, include_in_schema=False)
app.include_router(url_shortener.app, include_in_schema=False)
app.include_router(paypal.router, include_in_schema=False)
app.include_router(stripe.router, include_in_schema=False)
app.include_router(twilio_api.router, include_in_schema=False)
app.include_router(static_pages.app, include_in_schema=False)
app.include_router(root.app, include_in_schema=False)  # this has a catch-all route

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthenticationMiddleware, backend=SessionAuthBackend())
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)


# monkey patch to make django db work with fastapi
for route in app.routes:
    if isinstance(route, APIRoute) and not is_async_callable(route.endpoint):
        route.endpoint = db_middleware(route.endpoint)


@app.on_event("startup")
async def startup():
    limiter = anyio.to_thread.current_default_thread_limiter()
    limiter.total_tokens = config("MAX_THREADS", default=limiter.total_tokens, cast=int)


@app.add_middleware
def request_time_middleware(app):
    logger = logging.getLogger("uvicorn.time")

    async def middleware(scope, receive, send):
        start_time = time()
        await app(scope, receive, send)
        response_time = (time() - start_time) * 1000
        logger.info(
            f"{scope.get('method')} {scope.get('path')} - {response_time:.3f} ms"
        )

    return middleware


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    ## https://fastapi.tiangolo.com/tutorial/handling-errors/#override-request-validation-exceptions
    convert_errors(exc.errors())
    return await request_validation_exception_handler(request, exc)


@app.exception_handler(HTTP_404_NOT_FOUND)
@app.exception_handler(HTTP_405_METHOD_NOT_ALLOWED)
async def not_found_exception_handler(request: Request, exc: HTTPException):
    return await _exc_handler(request, exc, "errors/404.html")


@app.exception_handler(Exception)
async def server_error_exception_handler(request: Request, exc: Exception):
    return await _exc_handler(request, exc, "errors/unknown.html")


async def _exc_handler(request: Request, exc: Exception, template_name: str):
    from celeryapp.tasks import err_msg_for_exc

    if request.headers.get("accept", "").startswith("text/html"):
        return templates.TemplateResponse(
            template_name,
            context=dict(
                request=request,
                settings=settings,
                error=err_msg_for_exc(exc),
                github_url=github_url_for_exc(exc),
                traceback=traceback.format_exc(),
            ),
            status_code=getattr(exc, "status_code", 500),
        )
    elif isinstance(exc, HTTPException):
        return await http_exception_handler(request, exc)
    else:
        return JSONResponse(dict(detail=err_msg_for_exc(exc)), status_code=500)


GITHUB_REPO = "https://github.com/GooeyAI/gooey-server/"


def github_url_for_exc(exc: Exception) -> str | None:
    base_dir = str(settings.BASE_DIR)
    ref = (os.environ.get("CAPROVER_GIT_COMMIT_SHA") or "master").strip()
    for frame in reversed(traceback.extract_tb(exc.__traceback__)):
        if not frame.filename.startswith(base_dir):
            continue
        path = os.path.relpath(frame.filename, base_dir)
        return str(
            furl(GITHUB_REPO, fragment_path=f"L{frame.lineno}") / "blob" / ref / path
        )
    return GITHUB_REPO
