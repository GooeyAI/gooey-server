# Header encoding (see RFC5987)
import requests
from fastapi import HTTPException
from starlette.requests import Request

from daras_ai_v2 import settings

keyword = "Token"
HTTP_HEADER_ENCODING = 'iso-8859-1'


def get_authorization_header(request: Request):
    """
    Return request's 'Authorization:' header, as a bytestring.
    Hide some test client ickyness where the header can be unicode.
    """
    auth = request.headers.get('AUTHORIZATION', b'')
    if isinstance(auth, str):
        # Work around django test client oddness
        auth = auth.encode(HTTP_HEADER_ENCODING)
    return auth


def authenticate(request):
    auth = get_authorization_header(request).split()
    if not auth or auth[0].lower() != keyword.lower().encode():
        return None
    if len(auth) == 1:
        msg = 'Invalid token header. No credentials provided.'
        raise Exception(msg)
    elif len(auth) > 2:
        msg = 'Invalid token header. Token string should not contain spaces.'
        raise Exception(msg)

    try:
        token = auth[1].decode()
    except UnicodeError:
        msg = 'Invalid token header. Token string should not contain invalid characters.'
        raise Exception(msg)
    return authenticate_credentials(token)


def authenticate_credentials(token: str):
    if token != settings.API_SECRET_KEY:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "INVALID API TOKEN",
            },
        )
