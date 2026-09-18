"""
Integration endpoints for the ComfyUI cloud gateway (comfy.gooey.ai).

The gateway is a separate service (see comfy/README.md). It relies on
gooey-server for two things:

1. Browser SSO: `GET /comfy/sso/` runs on gooey.ai where the user's session
   cookie is visible, mints a short-lived signed token and redirects back to
   the gateway, which exchanges it via the internal API below.

2. Internal service API (`/__/comfy/api/*`): authenticated with the shared
   `COMFY_SERVICE_TOKEN` bearer token. Lets the gateway resolve the user's
   workspaces and bill GPU usage to a workspace using the same idempotent
   `Workspace.add_balance` primitive used by recipe runs.
"""

import uuid
from urllib.parse import urlparse

import fastapi
from fastapi import Depends, Header
from furl import furl
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel
from starlette.responses import RedirectResponse
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_402_PAYMENT_REQUIRED

from app_users.models import AppUser
from daras_ai_v2 import settings
from routers.custom_api_router import CustomAPIRouter
from workspaces.models import Workspace

app = CustomAPIRouter()

COMFY_SSO_SALT = "gooey-comfy-sso"
COMFY_SSO_TOKEN_MAX_AGE = 5 * 60  # short-lived: only exists during the redirect

_sso_signer = URLSafeTimedSerializer(settings.SECRET_KEY, salt=COMFY_SSO_SALT)


## ---------------------------------------------------------------------------
## Browser SSO handshake
## ---------------------------------------------------------------------------


@app.get("/comfy/sso/")
def comfy_sso(request: fastapi.Request):
    """
    Entry point for logging into comfy.gooey.ai with the Gooey account.
    Requires an active gooey.ai session; otherwise bounces via /login/ first.
    """
    from routers.base_auth import get_login_url

    if not request.user or request.user.is_anonymous:
        return RedirectResponse(get_login_url(request))

    token = _sso_signer.dumps({"uid": request.user.uid})
    callback = furl(settings.COMFY_BASE_URL).add(path="auth/callback")
    callback.query.params["token"] = token

    next_url = request.query_params.get("next")
    if next_url and _is_comfy_relative_path(next_url):
        callback.query.params["next"] = next_url

    return RedirectResponse(str(callback))


def _is_comfy_relative_path(next_url: str) -> bool:
    # only allow paths on the comfy origin itself, never absolute URLs
    parsed = urlparse(next_url)
    return not parsed.scheme and not parsed.netloc and next_url.startswith("/")


## ---------------------------------------------------------------------------
## Internal service API (gateway -> gooey-server)
## ---------------------------------------------------------------------------


def comfy_service_auth(authorization: str = Header(default="")):
    parts = authorization.split()
    if (
        not settings.COMFY_SERVICE_TOKEN
        or len(parts) != 2
        or parts[0].lower() != "bearer"
        or parts[1] != settings.COMFY_SERVICE_TOKEN
    ):
        raise fastapi.HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid comfy service token."},
        )


class WorkspaceInfo(BaseModel):
    id: int
    name: str
    balance: int
    is_personal: bool
    photo_url: str


class ComfyUserInfo(BaseModel):
    uid: str
    display_name: str
    email: str | None
    photo_url: str
    is_disabled: bool
    workspaces: list[WorkspaceInfo]


def _workspace_info(w: Workspace, user: AppUser) -> WorkspaceInfo:
    return WorkspaceInfo(
        id=w.id,
        name=w.display_name(user),
        balance=w.balance,
        is_personal=w.is_personal,
        photo_url=w.get_photo(),
    )


def _user_info(user: AppUser) -> ComfyUserInfo:
    return ComfyUserInfo(
        uid=user.uid,
        display_name=user.display_name,
        email=user.email,
        photo_url=user.get_photo(),
        is_disabled=user.is_disabled,
        workspaces=[_workspace_info(w, user) for w in user.cached_workspaces],
    )


class VerifySsoRequest(BaseModel):
    token: str


@app.post(
    "/__/comfy/api/verify-sso/",
    dependencies=[Depends(comfy_service_auth)],
    include_in_schema=False,
)
def comfy_verify_sso(payload: VerifySsoRequest) -> ComfyUserInfo:
    try:
        data = _sso_signer.loads(payload.token, max_age=COMFY_SSO_TOKEN_MAX_AGE)
    except SignatureExpired:
        raise fastapi.HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail={"error": "SSO token expired. Please login again."},
        )
    except BadSignature:
        raise fastapi.HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid SSO token."},
        )
    user = _get_user_or_401(data.get("uid") or "")
    return _user_info(user)


@app.get(
    "/__/comfy/api/users/{uid}/",
    dependencies=[Depends(comfy_service_auth)],
    include_in_schema=False,
)
def comfy_get_user(uid: str) -> ComfyUserInfo:
    """Refresh the user's profile + workspace balances (e.g. on workspace switch)."""
    return _user_info(_get_user_or_401(uid))


def _get_user_or_401(uid: str) -> AppUser:
    try:
        user = AppUser.objects.get(uid=uid)
    except AppUser.DoesNotExist:
        raise fastapi.HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail={"error": "User not found."},
        )
    if user.is_disabled or user.is_anonymous:
        raise fastapi.HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail={"error": "This account cannot use ComfyUI cloud."},
        )
    return user


class ComfyUsageRequest(BaseModel):
    uid: str
    workspace_id: int
    gpu_ms: int
    # deterministic id from the gateway (e.g. f"comfy_{sandbox_id}_{minute}") so
    # retries never double-charge — add_balance is idempotent on invoice_id
    invoice_id: str
    note: str = ""


class ComfyUsageResponse(BaseModel):
    credits_charged: int
    balance: int


@app.post(
    "/__/comfy/api/usage/",
    dependencies=[Depends(comfy_service_auth)],
    include_in_schema=False,
)
def comfy_record_usage(payload: ComfyUsageRequest) -> ComfyUsageResponse:
    """
    Bill metered ComfyUI GPU time to a workspace. Pricing stays server-side
    (COMFY_CREDITS_PER_GPU_MINUTE) so the gateway only reports raw gpu_ms.
    """
    user = _get_user_or_401(payload.uid)
    workspace = _get_workspace_for_member_or_401(payload.workspace_id, user)

    credits = max(
        1, round(settings.COMFY_CREDITS_PER_GPU_MINUTE * payload.gpu_ms / 60_000)
    )
    if workspace.balance <= 0:
        raise fastapi.HTTPException(
            status_code=HTTP_402_PAYMENT_REQUIRED,
            detail={"error": "Insufficient credits.", "balance": workspace.balance},
        )
    txn = workspace.add_balance(
        amount=-credits,
        invoice_id=f"gooey_in_comfy_{uuid.uuid5(uuid.NAMESPACE_URL, payload.invoice_id)}",
        user=user,
    )
    return ComfyUsageResponse(credits_charged=credits, balance=txn.end_balance)


class ComfyBalanceResponse(BaseModel):
    balance: int


@app.get(
    "/__/comfy/api/workspaces/{workspace_id}/balance/",
    dependencies=[Depends(comfy_service_auth)],
    include_in_schema=False,
)
def comfy_workspace_balance(workspace_id: int, uid: str) -> ComfyBalanceResponse:
    user = _get_user_or_401(uid)
    workspace = _get_workspace_for_member_or_401(workspace_id, user)
    return ComfyBalanceResponse(balance=workspace.balance)


def _get_workspace_for_member_or_401(workspace_id: int, user: AppUser) -> Workspace:
    try:
        return Workspace.objects.get(
            id=workspace_id,
            memberships__user=user,
            memberships__deleted__isnull=True,
        )
    except Workspace.DoesNotExist:
        raise fastapi.HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail={"error": "You are not a member of this workspace."},
        )
