from contextlib import contextmanager

from starlette.authentication import AuthCredentials, AuthenticationBackend
from starlette.concurrency import run_in_threadpool

from bots.models import get_default_published_run_workspace
from daras_ai_v2 import settings
from gooeysite.bg_db_conn import db_middleware
from workspaces.models import Workspace

# quick and dirty way to bypass authentication for testing
authlocal = []


@contextmanager
def force_authentication():
    user = Workspace.objects.get(id=get_default_published_run_workspace()).created_by
    user.email = "test@pytest.com"
    user.balance = 10**9
    user.disable_rate_limits = True
    user.save()
    authlocal.append(user)
    try:
        yield authlocal[0]
    finally:
        authlocal.clear()


class SessionAuthBackend(AuthenticationBackend):
    async def authenticate(self, conn):
        if authlocal:
            return AuthCredentials(["authenticated"]), authlocal[0]
        return await run_in_threadpool(_authenticate, conn)


@db_middleware
def _authenticate(conn):
    if settings.ENABLE_FIREBASE_AUTH:
        from routers.firebase_auth import authenticate_session
    else:
        from routers.local_auth import authenticate_session

    user = authenticate_session(conn.session)
    if user:
        return AuthCredentials(["authenticated"]), user
    else:
        return AuthCredentials(), None
