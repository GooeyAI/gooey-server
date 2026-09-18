"""Signed-cookie sessions for the gateway (mirrors gooey-server's approach)."""

import typing

from fastapi import Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from gateway import settings

_signer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="comfy-gateway-session")


class Session(typing.TypedDict):
    uid: str
    display_name: str
    photo_url: str
    workspaces: list[dict]  # [{id, name, balance, is_personal, photo_url}]
    selected_workspace_id: int


def get_session(request: Request) -> Session | None:
    cookie = request.cookies.get(settings.SESSION_COOKIE)
    if not cookie:
        return None
    try:
        return _signer.loads(cookie, max_age=settings.SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def set_session(response: Response, session: Session):
    response.set_cookie(
        settings.SESSION_COOKIE,
        _signer.dumps(session),
        max_age=settings.SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=settings.COMFY_BASE_URL.startswith("https"),
    )


def clear_session(response: Response):
    response.delete_cookie(settings.SESSION_COOKIE)


def session_from_user_info(
    user_info: dict, selected_workspace_id: int | None = None
) -> Session:
    workspaces = user_info["workspaces"]
    workspace_ids = [w["id"] for w in workspaces]
    if selected_workspace_id not in workspace_ids:
        selected_workspace_id = workspace_ids[0]
    return Session(
        uid=user_info["uid"],
        display_name=user_info["display_name"],
        photo_url=user_info["photo_url"],
        workspaces=workspaces,
        selected_workspace_id=selected_workspace_id,
    )
