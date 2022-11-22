from starlette.authentication import AuthCredentials, AuthenticationBackend

from daras_ai_v2.st_session_cookie import get_user_from_session

FIREBASE_SESSION = "firebase-session"


class SessionAuthBackend(AuthenticationBackend):
    async def authenticate(self, conn):
        session_cookie = conn.cookies.get(FIREBASE_SESSION)
        if not session_cookie:
            # Session cookie is unavailable. Force user to login.
            return AuthCredentials(), None

        user = get_user_from_session(session_cookie)
        if not user:
            return AuthCredentials(), None

        return AuthCredentials(["authenticated"]), user
