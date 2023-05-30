from contextlib import contextmanager

from firebase_admin import auth
from firebase_admin.auth import UserRecord
from starlette.authentication import AuthCredentials, AuthenticationBackend
from starlette.concurrency import run_in_threadpool

from app_users.models import AppUser
from daras_ai_v2.db import FIREBASE_SESSION_COOKIE, ANONYMOUS_USER_COOKIE

# quick and dirty way to bypass authentication for testing
_forced_auth_user = []


@contextmanager
def force_authentication():
    user = AppUser.objects.create(is_anonymous=True, balance=1000)
    try:
        _forced_auth_user.append(user)
        yield
    finally:
        _forced_auth_user.clear()


class SessionAuthBackend(AuthenticationBackend):
    async def authenticate(self, conn):
        return await run_in_threadpool(authenticate, conn)


def authenticate(conn):
    if _forced_auth_user:
        return AuthCredentials(["authenticated"]), _forced_auth_user[0]

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

    user = verify_session_cookie(session_cookie)
    if not user:
        # Session cookie was invalid
        conn.session.pop(FIREBASE_SESSION_COOKIE, None)
        return AuthCredentials(), None

    return AuthCredentials(["authenticated"]), user


def verify_session_cookie(firebase_cookie: str) -> UserRecord | None:
    # Verify the session cookie. In this case an additional check is added to detect
    # if the user's Firebase session was revoked, user deleted/disabled, etc.
    try:
        decoded_claims = auth.verify_session_cookie(firebase_cookie)
        return AppUser.objects.get_or_create_from_uid(decoded_claims["uid"])[0]
    except (auth.UserNotFoundError, auth.InvalidSessionCookieError):
        # Session cookie is invalid, expired or revoked. Force user to login.
        return None
