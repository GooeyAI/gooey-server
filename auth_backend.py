import uuid
from contextlib import contextmanager
from time import time

from firebase_admin import auth
from firebase_admin.auth import UserRecord
from starlette.authentication import AuthCredentials, AuthenticationBackend

from daras_ai_v2 import db
from daras_ai_v2.db import FIREBASE_SESSION_COOKIE

# quick and dirty way to bypass authentication for testing
_forced_auth_user = []


@contextmanager
def force_authentication(user: UserRecord = None):
    is_temp_user = not user
    if is_temp_user:
        user = auth.create_user()
        db.update_user_balance(user.uid, abs(1000), f"gooey_test_in_{uuid.uuid1()}")
    try:
        _forced_auth_user.append(user)
        yield
    finally:
        if is_temp_user:
            auth.delete_user(user.uid)
        _forced_auth_user.clear()


class SessionAuthBackend(AuthenticationBackend):
    async def authenticate(self, conn):
        if _forced_auth_user:
            return AuthCredentials(["authenticated"]), _forced_auth_user[0]

        session_cookie = conn.session.get(FIREBASE_SESSION_COOKIE)
        if not session_cookie:
            # Session cookie is unavailable. Force user to login.
            return AuthCredentials(), None

        user = verify_session_cookie(session_cookie)
        if not user:
            # Session cookie was invalid
            conn.session.pop(FIREBASE_SESSION_COOKIE, None)
            return AuthCredentials(), None
        return AuthCredentials(["authenticated"]), user


def verify_session_cookie(firebase_cookie) -> UserRecord | None:
    # Verify the session cookie. In this case an additional check is added to detect
    # if the user's Firebase session was revoked, user deleted/disabled, etc.
    try:
        user = auth.verify_session_cookie(firebase_cookie)
        user = auth.get_user(user["uid"])
        return user
    except (auth.UserNotFoundError, auth.InvalidSessionCookieError):
        # Session cookie is invalid, expired or revoked. Force user to login.
        return None
