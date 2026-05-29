from contextlib import contextmanager

from firebase_admin import auth as firebase_auth
from starlette.authentication import AuthCredentials, AuthenticationBackend
from starlette.concurrency import run_in_threadpool

from app_users.models import AppUser
from bots.models import get_default_published_run_workspace
from daras_ai_v2 import settings
from daras_ai_v2.db import FIREBASE_SESSION_COOKIE, LOCAL_AUTH_SESSION_COOKIE
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
    if settings.SOVEREIGN_DEPLOY:
        session_cookie = conn.session.get(FIREBASE_SESSION_COOKIE)
        if not session_cookie:
            return AuthCredentials(), None
        user = _verify_firebase_session_cookie(session_cookie)
        if not user:
            conn.session.pop(FIREBASE_SESSION_COOKIE, None)
            return AuthCredentials(), None
        return AuthCredentials(["authenticated"]), user
    else:
        user_id = conn.session.get(LOCAL_AUTH_SESSION_COOKIE)
        if not user_id:
            return AuthCredentials(), None
        try:
            user = AppUser.objects.get(pk=user_id)
            return AuthCredentials(["authenticated"]), user
        except AppUser.DoesNotExist:
            conn.session.pop(LOCAL_AUTH_SESSION_COOKIE, None)
            return AuthCredentials(), None


def _verify_firebase_session_cookie(firebase_cookie: str) -> AppUser | None:
    # Verify the session cookie. In this case an additional check is added to detect
    # if the user's Firebase session was revoked, user deleted/disabled, etc.
    try:
        decoded_claims = firebase_auth.verify_session_cookie(firebase_cookie)
        return AppUser.objects.get_or_create_from_uid(decoded_claims["uid"])[0]
    except (firebase_auth.UserNotFoundError, firebase_auth.InvalidSessionCookieError):
        # Session cookie is invalid, expired or revoked. Force user to login.
        return None
