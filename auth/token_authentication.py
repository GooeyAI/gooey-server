from typing import Any

from fastapi import Request
from fastapi.exceptions import HTTPException
from fastapi.openapi.models import HTTPBase as HTTPBaseModel, SecuritySchemeType
from fastapi.security.base import SecurityBase
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

from api_keys.models import ApiKey
from auth.auth_backend import authlocal
from daras_ai_v2.crypto import PBKDF2PasswordHasher


class AuthenticationError(HTTPException):
    status_code = HTTP_401_UNAUTHORIZED

    def __init__(self, msg: str):
        super().__init__(status_code=self.status_code, detail={"error": msg})


class AuthorizationError(HTTPException):
    status_code = HTTP_403_FORBIDDEN

    def __init__(self, msg: str):
        super().__init__(status_code=self.status_code, detail={"error": msg})


def authenticate_credentials(token: str) -> ApiKey:
    hasher = PBKDF2PasswordHasher()
    secret_key_hash = hasher.encode(token)

    try:
        api_key = ApiKey.objects.select_related("workspace__created_by").get(
            hash=secret_key_hash
        )
    except ApiKey.DoesNotExist:
        raise AuthorizationError("Invalid API Key.")

    if api_key.workspace.created_by.is_disabled:
        msg = (
            "Your Gooey.AI account has been disabled for violating our Terms of Service. "
            "Contact us at support@gooey.ai if you think this is a mistake."
        )
        raise AuthenticationError(msg)

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
