from fastapi import Header
from fastapi.exceptions import HTTPException

from app_users.models import AppUser
from auth_backend import _forced_auth_user
from daras_ai_v2 import db
from daras_ai_v2.crypto import PBKDF2PasswordHasher

auth_keyword = "Bearer"


def api_auth_header(
    authorization: str = Header(
        alias="Authorization",
        description=f"{auth_keyword} $GOOEY_API_KEY",
    ),
) -> AppUser:
    if _forced_auth_user:
        return _forced_auth_user[0]

    return authenticate(authorization)


def authenticate(auth_token: str) -> AppUser:
    auth = auth_token.split()
    if not auth or auth[0].lower() != auth_keyword.lower():
        msg = "Invalid Authorization header."
        raise HTTPException(status_code=401, detail={"error": msg})
    if len(auth) == 1:
        msg = "Invalid Authorization header. No credentials provided."
        raise HTTPException(status_code=401, detail={"error": msg})
    elif len(auth) > 2:
        msg = "Invalid Authorization header. Token string should not contain spaces."
        raise HTTPException(status_code=401, detail={"error": msg})
    return authenticate_credentials(auth[1])


def authenticate_credentials(token: str) -> AppUser:
    db_collection = db.client.collection(db.API_KEYS_COLLECTION)
    hasher = PBKDF2PasswordHasher()
    secret_key_hash = hasher.encode(token)

    try:
        doc = (
            db_collection.where("secret_key_hash", "==", secret_key_hash)
            .limit(1)
            .get()[0]
        )
    except IndexError:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Invalid API Key.",
            },
        )

    uid = doc.get("uid")
    user = AppUser.objects.get_or_create_from_uid(uid)[0]
    if user.is_disabled:
        msg = (
            "Your Gooey.AI account has been disabled for violating our Terms of Service. "
            "Contact us at support@gooey.ai if you think this is a mistake."
        )
        raise HTTPException(status_code=401, detail={"error": msg})

    return user
