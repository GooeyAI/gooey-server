from firebase_admin import auth
from firebase_admin.auth import UserRecord
from starlette.authentication import AuthCredentials, AuthenticationBackend


FIREBASE_SESSION_COOKIE = "firebase_session"
ANONYMOUS_USER_COOKIE = "anonymous_user"


class SessionAuthBackend(AuthenticationBackend):
    async def authenticate(self, conn):
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
        user = auth.verify_session_cookie(firebase_cookie, check_revoked=True)
        user = auth.get_user(user["uid"])
        return user
    except (auth.UserNotFoundError, auth.InvalidSessionCookieError):
        # Session cookie is invalid, expired or revoked. Force user to login.
        return None
