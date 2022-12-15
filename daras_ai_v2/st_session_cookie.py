import json
from base64 import b64decode

import itsdangerous
from firebase_admin import auth
from itsdangerous import BadSignature
from starlette.requests import cookie_parser
from streamlit.web.server.websocket_headers import _get_websocket_headers

from auth_backend import (
    FIREBASE_SESSION_COOKIE,
    verify_session_cookie,
)
from daras_ai_v2 import settings, db
from st_call_js import st_call_js

IS_ANONYMOUS = "is_anonymous"


def get_anonymous_user() -> auth.UserRecord | None:
    uid = st_call_js(
        """
        sendDataToPython(top.firebase.auth().currentUser?.uid);
        top.firebase.auth().onAuthStateChanged((user) => {
            sendDataToPython(user?.uid);
        })
        """
    )
    if not uid:
        return None

    user = auth.get_user(uid)
    setattr(user, IS_ANONYMOUS, True)

    user_doc_ref = db.get_user_doc_ref(user.uid)
    if not user_doc_ref.get([]).exists:
        user_doc_ref.create(
            {
                db.USER_BALANCE_FIELD: settings.ANON_USER_FREE_CREDITS,
                IS_ANONYMOUS: True,
            }
        )

    return user


def is_anonymous_user(user: auth.UserRecord) -> bool:
    return getattr(user, IS_ANONYMOUS, False)


def get_signed_in_user() -> auth.UserRecord | None:
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
    try:
        data = signer.unsign(data, max_age=max_age)
        session = json.loads(b64decode(data))
    except BadSignature:
        return {}
    return session
