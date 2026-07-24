import fastapi
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from fastapi.responses import JSONResponse
from furl import furl
from pydantic import BaseModel

import gooey_gui as gui
from app_users.models import AppUser
from daras_ai_v2 import settings
from daras_ai_v2.fastapi_tricks import get_route_path
from daras_ai_v2.meta_content import raw_build_meta_tags
from routers.base_auth import (
    DEFAULT_LOGIN_REDIRECT,
    safe_next_url,
)
from routers.custom_api_router import CustomAPIRouter
from routers.root import sidebar_page_wrapper, get_og_url_path

# mirrors django.contrib.auth
SESSION_KEY = "_auth_user_id"
HASH_SESSION_KEY = "_auth_user_hash"

app = CustomAPIRouter()


@gui.route(app, "/login/")
def login(request: fastapi.Request):
    if request.user and not request.user.is_anonymous:
        raise gui.RedirectException(
            safe_next_url(request.query_params, default=DEFAULT_LOGIN_REDIRECT)
        )

    submit_url = get_route_path(login_submit)
    next_url = request.query_params.get("next") or ""
    if next_url:
        submit_url = str(furl(submit_url, query_params={"next": next_url}))

    with (
        sidebar_page_wrapper(request),
        gui.center(className="flex-grow-1 my-5"),
    ):
        gui.component(
            "LoginForm",
            submitUrl=submit_url,
            forgotPasswordUrl=get_route_path(forgot_password),
        )

    return dict(
        meta=raw_build_meta_tags(
            url=get_og_url_path(request),
            title="Login to Gooey.AI",
            description="Sign in for incredible Open source, shared AI workflows.",
            robots="noindex,nofollow",
        )
    )


@gui.route(app, "/login/forgot-password/")
def forgot_password(request: fastapi.Request):
    """
    Passwords can only be reset from the django admin (see
    AppUserAdmin.user_change_password). This page takes an email and redirects
    to the admin password reset form for that user.
    """
    with (
        sidebar_page_wrapper(request),
        gui.center(className="flex-grow-1 my-5"),
    ):
        gui.component(
            "ForgotPasswordForm",
            submitUrl=get_route_path(forgot_password_submit),
            initialEmail=request.query_params.get("email") or "",
        )

    return dict(
        meta=raw_build_meta_tags(
            url=get_og_url_path(request),
            title="Reset password | Gooey.AI",
            description="Reset your Gooey.AI account password.",
            robots="noindex,nofollow",
        )
    )


class LoginRequest(BaseModel):
    email: str = ""
    password: str = ""


@app.post("/__/login/")
def login_submit(request: fastapi.Request, body: LoginRequest):
    email = body.email.strip().lower()
    password = body.password
    try:
        validate_email(email)
    except ValidationError:
        return JSONResponse(dict(error="Please enter a valid email address."))
    if not password:
        return JSONResponse(dict(error="Please enter a password."))

    user = authenticate_or_signup(email=email, password=password)
    if not user:
        return JSONResponse(dict(error="Incorrect email or password."))

    login_user(request, user)
    return JSONResponse(
        dict(
            redirect=safe_next_url(request.query_params, default=DEFAULT_LOGIN_REDIRECT)
        )
    )


class ForgotPasswordRequest(BaseModel):
    email: str = ""


@app.post("/__/login/forgot-password/")
def forgot_password_submit(body: ForgotPasswordRequest):
    email = body.email.strip().lower()
    user = None
    if email:
        user = AppUser.objects.filter(email=email).first()
    if not user:
        return JSONResponse(dict(error="No account found with that email."))
    return JSONResponse(
        dict(
            redirect=str(
                furl(settings.ADMIN_BASE_URL)
                / reverse("admin:app_users_appuser_password_change", args=[user.pk])
            )
        )
    )


def authenticate_or_signup(*, email: str, password: str) -> AppUser | None:
    """
    Mirrors django.contrib.auth.backends.ModelBackend.authenticate(),
    except that an unknown email signs up as a new user.
    """
    user, created = AppUser.objects.get_or_create_from_email(email)
    if user.is_disabled:
        return None
    if created or not user.has_usable_password():
        # newly signed up, or an existing account that never set a password
        # (e.g. migrated from firebase auth) -- set the password on first login
        user.set_password(password)
        user.save(update_fields=["password"])
        return user
    elif user.check_password(password):
        return user
    else:
        return None


def login_user(request: fastapi.Request, user: AppUser):
    """Mirrors django.contrib.auth.login() on top of starlette's cookie sessions"""
    session_auth_hash = user.get_session_auth_hash()
    if SESSION_KEY in request.session and (
        request.session[SESSION_KEY] != str(user.pk)
        or not session_hash_compare(request.session, session_auth_hash)
    ):
        # To avoid reusing another user's session, create a new, empty
        # session if the existing session corresponds to a different
        # authenticated user.
        request.session.clear()
    request.session[SESSION_KEY] = str(user.pk)
    request.session[HASH_SESSION_KEY] = session_auth_hash

    user.last_login_at = timezone.now()
    user.save(update_fields=["last_login_at"])


def authenticate_session(session: dict) -> AppUser | None:
    """mirrors django.contrib.auth.get_user()"""
    user_pk = session.get(SESSION_KEY)
    if not user_pk:
        return None

    try:
        user = AppUser.objects.get(pk=user_pk)
    except AppUser.DoesNotExist:
        # Session was invalid. Force user to login.
        user = None
        session.pop(SESSION_KEY, None)
        session.pop(HASH_SESSION_KEY, None)
    else:
        # verify the session hash so that password changes invalidate old sessions
        if user.is_disabled or not session_hash_compare(
            session, user.get_session_auth_hash()
        ):
            session.clear()
            user = None

    return user


def session_hash_compare(session: dict, user_hash: str) -> bool:
    session_hash = session.get(HASH_SESSION_KEY)
    return session_hash and constant_time_compare(session_hash, user_hash)
