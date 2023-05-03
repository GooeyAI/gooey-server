import streamlit2 as st
import json
from base64 import b64decode

import itsdangerous
from firebase_admin import auth
from itsdangerous import BadSignature
from starlette.requests import cookie_parser
from streamlit2 import _get_websocket_headers

from auth_backend import (
    FIREBASE_SESSION_COOKIE,
    verify_session_cookie,
)
from daras_ai_v2 import settings
from daras_ai_v2.db import ANONYMOUS_USER_COOKIE


def get_anonymous_user() -> auth.UserRecord | None:
    return auth.get_user_by_email("dev@dara.network")
    session = get_request_session()
    uid = session.get(ANONYMOUS_USER_COOKIE, {}).get("uid")
    if not uid:
        return None
    user = auth.get_user(uid)
    user._is_anonymous = True
    return user


def get_current_user() -> auth.UserRecord | None:
    return auth.get_user_by_email("dev@dara.network")
    session = get_request_session()
    if not session:
        return None
    firebase_cookie = session.get(FIREBASE_SESSION_COOKIE)
    if not firebase_cookie:
        return None
    user = verify_session_cookie(firebase_cookie)
    if user and user.disabled:
        msg = (
            "Your Gooey.AI account has been disabled for violating our [Terms of Service](/terms). "
            "Contact us at support@gooey.ai if you think this is a mistake."
        )
        st.error(msg, icon="😵")
        st.stop()
    return user


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
    try:
        data = signer.unsign(data, max_age=max_age)
        session = json.loads(b64decode(data))
    except BadSignature:
        return {}
    return session
