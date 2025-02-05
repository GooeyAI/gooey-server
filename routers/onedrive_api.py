import json

import requests
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from furl import furl
from starlette.requests import Request
from starlette.responses import HTMLResponse

from bots.models import SavedRun
from daras_ai_v2 import settings
from daras_ai_v2.exceptions import raise_for_status
from routers.custom_api_router import CustomAPIRouter

app = CustomAPIRouter()


@app.get("/__/onedrive/connect/")
def onedrive_connect_redirect(request: Request):
    from daras_ai_v2.base import SUBMIT_AFTER_LOGIN_Q

    if not request.user or request.user.is_anonymous:
        redirect_url = furl("/login", query_params={"next": request.url})
        return RedirectResponse(str(redirect_url))

    code = request.query_params.get("code")
    if not code:
        error = request.query_params.get("error")
        error_description = request.query_params.get("error_description")
        return HTMLResponse(
            f"Authorization code missing! {error} : {error_description}",
            status_code=400,
        )

    user_access_token, user_refresh_token = _get_access_token_from_code(code)
    user_display_name = _get_user_display_name(user_access_token)

    sr = load_sr_from_state(request)

    sr.workspace.onedrive_access_token = user_access_token
    sr.workspace.onedrive_refresh_token = user_refresh_token
    sr.workspace.onedrive_user_name = user_display_name
    sr.workspace.save(
        update_fields=[
            "onedrive_access_token",
            "onedrive_refresh_token",
            "onedrive_user_name",
        ]
    )

    redirect_url = sr.get_app_url({SUBMIT_AFTER_LOGIN_Q: "1"})
    return RedirectResponse(redirect_url.url)


def generate_onedrive_auth_url(sr_id: int) -> str:
    """Build the Microsoft OAuth URL to start interactive authorization.

    Returns:
        str: Fully constructed OAuth authorization URL
    """
    return furl(
        "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        query_params={
            "client_id": settings.ONEDRIVE_CLIENT_ID,
            "redirect_uri": onedrive_connect_redirect_url,
            "response_type": "code",
            "scope": ",".join(
                [
                    "Files.Read.All",
                    "offline_access",
                    "User.Read",
                ]
            ),
            "state": json.dumps(dict(sr_id=sr_id)),
        },
    ).tostr()


def load_sr_from_state(request: Request) -> SavedRun:
    sr_id = json.loads(request.query_params.get("state") or "{}").get("sr_id")
    try:
        return SavedRun.objects.get(id=sr_id)
    except SavedRun.DoesNotExist:
        raise HTTPException(status_code=404, detail="Published Run not found")


def _get_user_display_name(code: str) -> str:
    r = requests.get(
        url="https://graph.microsoft.com/v1.0/me",
        headers={"Authorization": f"Bearer {code}"},
    )
    raise_for_status(r)
    return r.json()["displayName"]


def _get_access_token_from_code(code: str) -> tuple[str, str]:
    r = requests.post(
        url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
        data={
            "client_id": settings.ONEDRIVE_CLIENT_ID,
            "client_secret": settings.ONEDRIVE_CLIENT_SECRET,
            "redirect_uri": onedrive_connect_redirect_url,
            "grant_type": "authorization_code",
            "code": code,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    raise_for_status(r)
    data = r.json()
    return data["access_token"], data["refresh_token"]


def get_access_token_from_refresh_token(refresh_token: str) -> tuple[str, str]:
    # https://learn.microsoft.com/en-us/onedrive/developer/rest-api/getting-started/graph-oauth?view=odsp-graph-online
    r = requests.post(
        "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        data={
            "client_id": settings.ONEDRIVE_CLIENT_ID,
            "client_secret": settings.ONEDRIVE_CLIENT_SECRET,
            "redirect_uri": onedrive_connect_redirect_url,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    raise_for_status(r)
    data = r.json()
    return data["access_token"], data["refresh_token"]


onedrive_connect_redirect_url = (
    furl(settings.APP_BASE_URL) / app.url_path_for(onedrive_connect_redirect.__name__)
).tostr()
