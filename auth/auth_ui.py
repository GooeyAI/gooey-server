from __future__ import annotations

import datetime
import traceback
import uuid
from time import time

import sentry_sdk
from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone
from fastapi import Request
from fastapi.responses import RedirectResponse
from furl import furl
from starlette.responses import PlainTextResponse, Response

import gooey_gui as gui
from app_users.models import AppUser
from daras_ai_v2.db import FIREBASE_SESSION_COOKIE, LOCAL_AUTH_SESSION_COOKIE
from daras_ai_v2 import settings
from daras_ai_v2.fastapi_tricks import get_route_path, resolve_url
from daras_ai_v2.meta_content import raw_build_meta_tags
from daras_ai_v2.settings import templates
from routers.custom_api_router import CustomAPIRouter


firebase_auth_router = CustomAPIRouter()
local_auth_router = CustomAPIRouter()

DEFAULT_LOGIN_REDIRECT = "/explore/"
DEFAULT_LOGOUT_REDIRECT = "/"


def _safe_next_url(query_params, *, default: str) -> str:
    next_url = query_params.get("next") or default
    if not next_url.startswith("/") or next_url.startswith("//"):
        return default
    return next_url


@firebase_auth_router.get("/logout/")
@local_auth_router.get("/logout/")
async def logout_route(request: Request) -> Response:
    request.session.clear()
    next_url = _safe_next_url(request.query_params, default=DEFAULT_LOGOUT_REDIRECT)
    return RedirectResponse(next_url)


@firebase_auth_router.get("/login/")
def firebase_login_route(request: Request) -> Response:
    from routers.account import invitation_route, load_invite_from_hashid_or_404

    if request.user and not request.user.is_anonymous:
        next_url = _safe_next_url(request.query_params, default=DEFAULT_LOGIN_REDIRECT)
        return RedirectResponse(next_url)

    login_sso_url = get_route_path(firebase_login_sso_route)
    if raw_next := request.query_params.get("next"):
        login_sso_url = str(furl(login_sso_url, query_params={"next": raw_next}))

    context = {"request": request, "login_sso_url": login_sso_url}

    try:
        if (
            (next_url := request.query_params.get("next"))
            and (match := resolve_url(next_url))
            and match.route.name == invitation_route.__name__
            and (invite_id := match.matched_params.get("invite_id"))
        ):
            context["invite"] = load_invite_from_hashid_or_404(invite_id)
    except Exception as e:
        traceback.print_exc()
        sentry_sdk.capture_exception(e)

    return templates.TemplateResponse("login_options.html", context=context)


@firebase_auth_router.get("/login/sso/")
def firebase_login_sso_route(request: Request) -> Response:
    if request.user and not request.user.is_anonymous:
        next_url = _safe_next_url(request.query_params, default=DEFAULT_LOGIN_REDIRECT)
        return RedirectResponse(next_url)

    login_url = get_route_path(firebase_login_route)
    if raw_next := request.query_params.get("next"):
        login_url = str(furl(login_url, query_params={"next": raw_next}))

    context = {"request": request, "login_url": login_url}
    return templates.TemplateResponse("login_sso.html", context=context)


@firebase_auth_router.post("/login/")
async def firebase_login_route_post(request: Request):
    from firebase_admin import auth, exceptions

    ## Taken from https://firebase.google.com/docs/auth/admin/manage-cookies#create_session_cookie
    form = await request.form()
    id_token = form.get("idToken", "")
    # To ensure that cookies are set only on recently signed in users, check auth_time in
    # ID token before creating a cookie.
    try:
        decoded_claims = auth.verify_id_token(id_token)
        # Only process if the user signed in within the last 5 minutes.
        if time() - decoded_claims["auth_time"] < 5 * 60:
            expires_in = datetime.timedelta(days=14)
            session_cookie = auth.create_session_cookie(id_token, expires_in=expires_in)
            request.session[FIREBASE_SESSION_COOKIE] = session_cookie
            uid = decoded_claims["uid"]
            # upgrade an anonymous account to a permanent account
            try:
                existing_user = AppUser.objects.get(uid=uid)
                if existing_user.is_anonymous:
                    existing_user.copy_from_firebase_user(auth.get_user(uid))
            except AppUser.DoesNotExist:
                pass
            else:
                existing_user.last_login_at = timezone.now()
                existing_user.save(update_fields=["last_login_at"])
            return RedirectResponse(
                _safe_next_url(request.query_params, default=DEFAULT_LOGIN_REDIRECT),
                status_code=303,
            )
        # User did not sign in recently. To guard against ID token theft, require
        # re-authentication.
        return PlainTextResponse(status_code=401, content="Recent sign in required")
    except auth.InvalidIdTokenError:
        return PlainTextResponse(status_code=401, content="Invalid ID token")
    except exceptions.FirebaseError:
        return PlainTextResponse(
            status_code=401, content="Failed to create a session cookie"
        )


@gui.route(local_auth_router, "/login/")
def local_login_route(request: Request):
    from routers.root import get_og_url_path, page_wrapper

    if request.user and not request.user.is_anonymous:
        next_url = _safe_next_url(request.query_params, default=DEFAULT_LOGIN_REDIRECT)
        return RedirectResponse(next_url)

    next_url = _safe_next_url(request.query_params, default=DEFAULT_LOGIN_REDIRECT)
    with page_wrapper(request):
        with gui.div(
            className="d-flex justify-content-center align-items-start pt-5 m-3"
        ):
            with gui.div(
                className="card shadow-sm",
                style=dict(width="100%", maxWidth="420px"),
            ):
                with gui.div(className="card-body p-4"):
                    with gui.div(className="text-center mb-4"):
                        gui.html("<h4>Sign in to Gooey.AI</h4>")

                    (sign_in_tab, sign_up_tab), _ = gui.controllable_tabs(
                        ["Sign in", "Sign up"], key="login:tab"
                    )

                    with sign_in_tab, gui.div(className="my-2"):
                        error_slot = gui.div()
                        email = gui.text_input(
                            "Email",
                            key="signin:email",
                            placeholder="you@example.com",
                        )
                        password = gui.password_input("Password", key="signin:password")
                        if gui.button(
                            "Sign in",
                            key="signin:btn",
                            type="primary",
                            className="w-100 btn-theme",
                        ):
                            email = (email or "").strip().lower()
                            if not email or not password:
                                with error_slot:
                                    gui.error("Email and password are required.")
                            else:
                                try:
                                    user = AppUser.objects.get(email=email)
                                except AppUser.DoesNotExist:
                                    with error_slot:
                                        gui.error("Invalid email or password.")
                                else:
                                    if (
                                        not user.localauth_password
                                        or not check_password(
                                            password, user.localauth_password
                                        )
                                    ):
                                        with error_slot:
                                            gui.error("Invalid email or password.")
                                    else:
                                        user.last_login_at = timezone.now()
                                        user.save(update_fields=["last_login_at"])
                                        request.session.clear()
                                        request.session[LOCAL_AUTH_SESSION_COOKIE] = (
                                            user.pk
                                        )
                                        return RedirectResponse(
                                            next_url, status_code=303
                                        )
                            gui.session_state.pop("signin:password", None)

                    with sign_up_tab, gui.div(className="my-2"):
                        error_slot = gui.div()
                        email = gui.text_input(
                            "Email",
                            key="signup:email",
                            placeholder="you@example.com",
                        )
                        password = gui.password_input("Password", key="signup:password")
                        confirm = gui.password_input(
                            "Confirm password", key="signup:confirm"
                        )
                        if gui.button(
                            "Create account",
                            key="signup:btn",
                            type="primary",
                            className="w-100 btn-theme",
                        ):
                            email = (email or "").strip().lower()
                            if not email or not password or not confirm:
                                with error_slot:
                                    gui.error("All fields are required.")
                            elif password != confirm:
                                with error_slot:
                                    gui.error("Passwords do not match.")
                            elif AppUser.objects.filter(email=email).exists():
                                with error_slot:
                                    gui.error(
                                        "An account with this email already exists."
                                    )
                            else:
                                user = AppUser.objects.create(
                                    uid=str(uuid.uuid4()),
                                    email=email,
                                    display_name=email.split("@")[0],
                                    is_anonymous=False,
                                    balance=settings.VERIFIED_EMAIL_USER_FREE_CREDITS,
                                    localauth_password=make_password(password),
                                    last_login_at=timezone.now(),
                                )
                                request.session.clear()
                                request.session[LOCAL_AUTH_SESSION_COOKIE] = user.pk
                                user.get_or_create_personal_workspace()
                                return RedirectResponse(next_url, status_code=303)
                            gui.session_state.pop("signup:password", None)
                            gui.session_state.pop("signup:confirm", None)

    return dict(
        meta=raw_build_meta_tags(
            url=get_og_url_path(request), title="Sign in to Gooey.AI"
        )
    )
