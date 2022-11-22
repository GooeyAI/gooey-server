import json
from base64 import b64decode

import itsdangerous
from starlette.requests import cookie_parser
from streamlit.web.server.websocket_headers import _get_websocket_headers

from daras_ai_v2 import settings


def get_current_user() -> dict | None:
    return get_current_session().get("user")


#
# Code stolen from starlette/middleware/sessions.py
#
max_age = 14 * 24 * 60 * 60  # 14 days, in seconds
signer = itsdangerous.TimestampSigner(str(settings.SECRET_KEY))


def get_current_session() -> dict:
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
