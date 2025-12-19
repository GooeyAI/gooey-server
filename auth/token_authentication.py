from typing import Any

from fastapi import Request
from fastapi.exceptions import HTTPException
from fastapi.openapi.models import HTTPBase as HTTPBaseModel, SecuritySchemeType
from fastapi.security.base import SecurityBase
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

from api_keys.models import ApiKey
from app_users.models import AppUser
from auth.auth_backend import authlocal
from bots.models.saved_run import SavedRun
from daras_ai_v2.crypto import PBKDF2PasswordHasher
from daras_ai_v2.settings import SECRET_KEY
from workspaces.models import Workspace


EPHEMERAL_KEY_PREFIX = "ek_"
EMERPHAL_KEY_SALT = "gooey-ephemeral-api-key"

TOKEN_EXPIRATION = 60 * 60 * 3  # 3 hours

DISABLED_ACCOUNT_ERROR_MESSAGE = (
    "This Gooey.AI account has been disabled for violating our [Terms of Service](https://gooey.ai/terms). "
    "Contact us at support@gooey.ai if you think this is a mistake."
)


class AuthenticationError(HTTPException):
    status_code = HTTP_401_UNAUTHORIZED

    def __init__(self, msg: str):
        super().__init__(status_code=self.status_code, detail={"error": msg})


class AuthorizationError(HTTPException):
    status_code = HTTP_403_FORBIDDEN

    def __init__(self, msg: str):
        super().__init__(status_code=self.status_code, detail={"error": msg})


def authenticate_credentials(token: str) -> ApiKey:
    if token.startswith(EPHEMERAL_KEY_PREFIX):
        return verify_ephemeral_api_key(token)

    hasher = PBKDF2PasswordHasher()
    secret_key_hash = hasher.encode(token)

    try:
        api_key = ApiKey.objects.select_related("workspace__created_by").get(
            hash=secret_key_hash
        )
    except ApiKey.DoesNotExist:
        raise AuthorizationError("Invalid API Key.")

    if api_key.workspace.created_by.is_disabled:
        raise AuthenticationError(DISABLED_ACCOUNT_ERROR_MESSAGE)

    return api_key


class APIAuth(SecurityBase):
    """
    ### Usage:

    ```python
    api_auth = APIAuth(scheme_name="bearer", description="Bearer $GOOEY_API_KEY")

    @app.get("/api/users")
    def get_users(authenticated_user: AppUser = Depends(api_auth)):
        ...
    ```
    """

    def __init__(
        self, scheme_name: str, description: str, openapi_extra: dict[str, Any] = None
    ):
        self.model = HTTPBaseModel(
            type=SecuritySchemeType.http,
            scheme=scheme_name,
            description=description,
            **(openapi_extra or {}),
        )
        self.scheme_name = scheme_name
        self.description = description

    def __call__(self, request: Request) -> ApiKey:
        if authlocal:  # testing only!
            return ApiKey(
                created_by=authlocal[0],
                workspace=authlocal[0].get_or_create_personal_workspace()[0],
            )

        auth = request.headers.get("Authorization", "").split()
        if not auth or auth[0].lower() != self.scheme_name.lower():
            raise AuthenticationError("Invalid Authorization header.")
        if len(auth) == 1:
            raise AuthenticationError(
                "Invalid Authorization header. No credentials provided."
            )
        elif len(auth) > 2:
            raise AuthenticationError(
                "Invalid Authorization header. Token string should not contain spaces."
            )
        return authenticate_credentials(auth[1])


auth_scheme = "bearer"
api_auth_header = APIAuth(
    scheme_name=auth_scheme,
    description=f"{auth_scheme} $GOOEY_API_KEY",
    openapi_extra={"x-fern-bearer": {"name": "apiKey", "env": "GOOEY_API_KEY"}},
)


_signer = URLSafeTimedSerializer(SECRET_KEY, salt=EMERPHAL_KEY_SALT)


def generate_ephemeral_api_key(user_id: int, workspace_id: str, run_id: str) -> str:
    payload = {
        "user_id": user_id,
        "workspace_id": workspace_id,
        "run_id": run_id,
    }
    signed_token = _signer.dumps(payload, salt=EMERPHAL_KEY_SALT)
    token = EPHEMERAL_KEY_PREFIX + signed_token

    return token


def verify_ephemeral_api_key(token: str) -> ApiKey:
    signed_token = token.removeprefix(EPHEMERAL_KEY_PREFIX)
    try:
        payload = _signer.loads(
            signed_token, salt=EMERPHAL_KEY_SALT, max_age=TOKEN_EXPIRATION
        )
    except SignatureExpired:
        raise AuthenticationError("API Key has expired.")
    except BadSignature:
        raise AuthenticationError("Invalid API Key.")

    workspace_id = payload.get("workspace_id")
    user_id = payload.get("user_id")
    run_id = payload.get("run_id")

    if not (workspace_id and user_id and run_id):
        raise AuthenticationError("Invalid API Key.")

    try:
        workspace = Workspace.objects.get(id=workspace_id)
        user = AppUser.objects.get(id=user_id)
    except (Workspace.DoesNotExist, AppUser.DoesNotExist):
        raise AuthenticationError("Invalid API Key.")

    if user.is_disabled or workspace.created_by.is_disabled:
        raise AuthorizationError(DISABLED_ACCOUNT_ERROR_MESSAGE)

    _verify_run_state(run_id, user)

    return ApiKey(created_by=user, workspace=workspace)


def _verify_run_state(run_id: str, user: AppUser) -> None:
    from daras_ai_v2.base import BasePage, RecipeRunState

    try:
        saved_run = SavedRun.objects.get(run_id=run_id, uid=user.uid)
    except SavedRun.DoesNotExist:
        raise AuthenticationError("Invalid API Key. Run not found.")

    state = saved_run.to_dict()
    run_state = BasePage.get_run_state(state)

    if run_state != RecipeRunState.running:
        raise AuthenticationError("Invalid API Key. Run is not active.")
