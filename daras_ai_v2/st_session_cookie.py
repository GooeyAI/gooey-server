from firebase_admin import auth
from starlette.requests import cookie_parser
from streamlit.web.server.websocket_headers import _get_websocket_headers


def get_current_user() -> dict | None:
    # https://github.com/streamlit/streamlit/pull/5457
    headers = _get_websocket_headers()

    try:
        cookies = cookie_parser(headers["Cookie"])
        data = cookies["session"].encode("utf-8")
    except KeyError:
        return None
    if not data:
        return None

    return get_user_from_session(data)


def get_user_from_session(session_cookie):
    # Verify the session cookie. In this case an additional check is added to detect
    # if the user's Firebase session was revoked, user deleted/disabled, etc.
    try:
        user = auth.verify_session_cookie(session_cookie, check_revoked=True)
        user["display_name"] = user.get(
            "name", user.get("email", user.get("phone_number"))
        )
        return user
    except auth.InvalidSessionCookieError:
        # Session cookie is invalid, expired or revoked. Force user to login.
        return None
