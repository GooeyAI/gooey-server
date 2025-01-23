import json

import requests
from fastapi.responses import RedirectResponse
from furl import furl
from starlette.requests import Request
from starlette.responses import HTMLResponse
from daras_ai_v2 import settings
from daras_ai_v2.exceptions import raise_for_status
from routers.custom_api_router import CustomAPIRouter
from workspaces.widgets import get_current_workspace
from loguru import logger

app = CustomAPIRouter()


def load_current_run_url_from_state(request: Request) -> furl:
    url = furl(
        json.loads(request.query_params.get("state") or "{}").get("current_app_url")
    )
    return url


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
        return HTMLResponse(f"Authorization code missing! {error} : {error_description}", status_code=400)

    redirect_url = load_current_run_url_from_state(request)
    user_access_token, user_refresh_token = _get_access_token_from_code(
        code, onedrive_connect_redirect_url
    )

    current_workspace = get_current_workspace(request.user, request.session)
    current_workspace.onedrive_access_token = user_access_token
    current_workspace.onedrive_refresh_token = user_refresh_token
    current_workspace.save(
        update_fields=["onedrive_access_token", "onedrive_refresh_token"]
    )

    redirect_url.add({SUBMIT_AFTER_LOGIN_Q: "1"})

    return RedirectResponse(redirect_url)


onedrive_connect_redirect_url = (
    furl(
        settings.APP_BASE_URL,
    )
    / app.url_path_for(onedrive_connect_redirect.__name__)
).tostr()


def generate_onedrive_auth_url(current_app_url: str) -> str:
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
                ]
            ),
            "state": json.dumps(dict(current_app_url=current_app_url)),
        },
    ).tostr()


def _get_access_token_from_code(
    code: str,
    redirect_uri: str,
):
    # url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    # logger.debug(
    #     f"{settings.ONEDRIVE_CLIENT_ID=} ,  {settings.ONEDRIVE_CLIENT_SECRET=}"
    # )

    # payload = {
    #     "client_id": settings.ONEDRIVE_CLIENT_ID,
    #     "client_secret": settings.ONEDRIVE_CLIENT_SECRET,
    #     "code": code,
    #     "redirect_uri": redirect_uri,
    #     "grant_type": "authorization_code",
    # }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    r = requests.post(
        url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
        data={
            "client_id": settings.ONEDRIVE_CLIENT_ID,
            "client_secret": settings.ONEDRIVE_CLIENT_SECRET,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        headers=headers,
    )
    raise_for_status(r)
    tokens = r.json()
    return tokens["access_token"], tokens["refresh_token"]


def get_access_token_from_refresh_token(refresh_token: str, redirect_uri: str) -> str:
    # https://learn.microsoft.com/en-us/onedrive/developer/rest-api/getting-started/graph-oauth?view=odsp-graph-online
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    r = requests.post(
        "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        data={
            "client_id": settings.ONEDRIVE_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "client_secret": settings.ONEDRIVE_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        headers=headers,
    )
    raise_for_status(r)
    return r.json()["access_token"]
