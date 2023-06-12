from gooeysite import wsgi

assert wsgi

from fastapi.routing import APIRoute
from starlette._utils import is_async_callable

from gooeysite.bg_db_conn import db_middleware

from time import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import (
    Response,
)

from auth_backend import (
    SessionAuthBackend,
)
from daras_ai_v2 import settings
from routers import billing, facebook, talkjs, api, root

app = FastAPI(title="GOOEY.AI", docs_url=None, redoc_url="/docs")

app.include_router(api.app)
app.include_router(billing.router, include_in_schema=False)
app.include_router(talkjs.router, include_in_schema=False)
app.include_router(facebook.router, include_in_schema=False)
app.include_router(root.app, include_in_schema=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthenticationMiddleware, backend=SessionAuthBackend())
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.middleware("http")
async def logger(request: Request, call_next):
    start_time = time()
    response: Response = await call_next(request)
    response_time = (time() - start_time) * 1000
    print(
        f"{request.method} {request.url} {response.status_code} {response.headers.get('content-length', '-')} - {response_time:.3f} ms"
    )
    return response


# monkey patch to make django db work with fastapi
for route in app.routes:
    if isinstance(route, APIRoute) and not is_async_callable(route.endpoint):
        route.endpoint = db_middleware(route.endpoint)
