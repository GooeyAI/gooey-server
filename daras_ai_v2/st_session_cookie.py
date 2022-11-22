import json
from base64 import b64decode

import itsdangerous
from firebase_admin import auth
from starlette.requests import cookie_parser
from streamlit.web.server.websocket_headers import _get_websocket_headers

from auth_backend import (
    FIREBASE_SESSION_COOKIE,
    verify_session_cookie,
    ANONYMOUS_USER_COOKIE,
)
from daras_ai_v2 import settings


def get_anonymous_user() -> auth.UserRecord | None:
    session = get_request_session()
    uid = session.get(ANONYMOUS_USER_COOKIE, {}).get("uid")
    if not uid:
        return None
    return auth.get_user(uid)


def get_current_user() -> auth.UserRecord | None:
    session = get_request_session()
    if not session:
        return None
    firebase_cookie = session.get(FIREBASE_SESSION_COOKIE)
    if not firebase_cookie:
        return None
    return verify_session_cookie(firebase_cookie)


#
# Code stolen from starlette/middleware/sessions.py
#
max_age = 14 * 24 * 60 * 60  # 14 days, in seconds
signer = itsdangerous.TimestampSigner(str(settings.SECRET_KEY))


def get_request_session() -> dict:
    # https://github.com/streamlit/streamlit/pull/5457
    headers = _get_websocket_headers()
    try:
        cookies = cookie_parser(headers["Cookie"])
        data = cookies["session"].encode("utf-8")
    except KeyError:
        return {}
    data = signer.unsign(data, max_age=max_age)
    session = json.loads(b64decode(data))
    return session
