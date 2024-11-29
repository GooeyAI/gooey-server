from contextlib import contextmanager

from firebase_admin import auth
from firebase_admin.auth import UserRecord
from starlette.authentication import AuthCredentials, AuthenticationBackend
from starlette.concurrency import run_in_threadpool

from app_users.models import AppUser
from bots.models import get_default_published_run_workspace
from daras_ai_v2.db import FIREBASE_SESSION_COOKIE, ANONYMOUS_USER_COOKIE
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
    session_cookie = conn.session.get(FIREBASE_SESSION_COOKIE)
    if not session_cookie:
        # Session cookie is unavailable. Check if anonymous user is available.
        anon_uid = conn.session.get(ANONYMOUS_USER_COOKIE, {}).get("uid")
        if anon_uid:
            try:
                anon_user = AppUser.objects.get(uid=anon_uid)
                if anon_user.is_anonymous:
                    return AuthCredentials(["authenticated"]), anon_user
            except AppUser.DoesNotExist:
                # Anonymous user was deleted
                conn.session.pop(ANONYMOUS_USER_COOKIE, None)
        # Session cookie is unavailable. Force user to login.
        return AuthCredentials(), None

    user = _verify_session_cookie(session_cookie)
    if not user:
        # Session cookie was invalid
        conn.session.pop(FIREBASE_SESSION_COOKIE, None)
        return AuthCredentials(), None

    return AuthCredentials(["authenticated"]), user


def _verify_session_cookie(firebase_cookie: str) -> UserRecord | None:
    # Verify the session cookie. In this case an additional check is added to detect
    # if the user's Firebase session was revoked, user deleted/disabled, etc.
    try:
        decoded_claims = auth.verify_session_cookie(firebase_cookie)
        return AppUser.objects.get_or_create_from_uid(decoded_claims["uid"])[0]
    except (auth.UserNotFoundError, auth.InvalidSessionCookieError):
        # Session cookie is invalid, expired or revoked. Force user to login.
        return None
