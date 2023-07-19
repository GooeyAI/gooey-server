import anyio
from decouple import config

from gooeysite import wsgi

assert wsgi

from time import time

from fastapi.routing import APIRoute
from starlette._utils import is_async_callable

from gooeysite.bg_db_conn import db_middleware

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.middleware.sessions import SessionMiddleware

from auth_backend import (
    SessionAuthBackend,
)
from daras_ai_v2 import settings
from routers import billing, facebook, talkjs, api, root
import url_shortener.routers as url_shortener

app = FastAPI(title="GOOEY.AI", docs_url=None, redoc_url="/docs")

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(api.app)
app.include_router(billing.router, include_in_schema=False)
app.include_router(talkjs.router, include_in_schema=False)
app.include_router(facebook.router, include_in_schema=False)
app.include_router(root.app, include_in_schema=False)
app.include_router(url_shortener.app, include_in_schema=False)

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


@app.get("/")
async def health():
    return "OK"


@app.add_middleware
def request_time_middleware(app):
    async def middleware(scope, receive, send):
        start_time = time()
        await app(scope, receive, send)
        response_time = (time() - start_time) * 1000
        print(f"{scope.get('method')} {scope.get('path')} - {response_time:.3f} ms")

    return middleware
