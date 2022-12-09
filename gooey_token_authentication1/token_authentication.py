# Header encoding (see RFC5987)
import requests
from fastapi import HTTPException
from starlette.requests import Request

from daras_ai_v2 import settings

keyword = "Token"


def authenticate(auth_token: str):
    auth = auth_token.split()
    if not auth or auth[0].lower() != keyword.lower():
        msg = "Invalid token header."
        raise HTTPException(status_code=401, detail={"error": msg})
    if len(auth) == 1:
        msg = "Invalid token header. No credentials provided."
        raise HTTPException(status_code=401, detail={"error": msg})
    elif len(auth) > 2:
        msg = "Invalid token header. Token string should not contain spaces."
        raise HTTPException(status_code=401, detail={"error": msg})
    authenticate_credentials(auth[1])


def authenticate_credentials(token: str):
    if token != settings.API_SECRET_KEY:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "INVALID API TOKEN",
            },
        )
