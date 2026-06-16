from __future__ import annotations

import datetime
import traceback
from time import time

import sentry_sdk
from django.utils import timezone
from fastapi.responses import RedirectResponse
from firebase_admin import auth
from firebase_admin.exceptions import FirebaseError
from furl import furl
from starlette.responses import PlainTextResponse

from app_users.models import AppUser
from daras_ai_v2 import settings
from daras_ai_v2.base import BasePageRequest
from daras_ai_v2.fastapi_tricks import (
    get_route_path,
    resolve_url,
)
from routers.custom_api_router import CustomAPIRouter
import fastapi
from routers.base_auth import DEFAULT_LOGIN_REDIRECT, safe_next_url
from daras_ai_v2.settings import templates

FIREBASE_SESSION_COOKIE = "firebase_session"
ANONYMOUS_USER_COOKIE = "anonymous_user"

app = CustomAPIRouter()


@app.get("/login/")
def login(request: fastapi.Request):
    from routers.account import invitation_route, load_invite_from_hashid_or_404

    if request.user and not request.user.is_anonymous:
        return RedirectResponse(
            safe_next_url(request.query_params, default=DEFAULT_LOGIN_REDIRECT)
        )

    login_sso_url = get_route_path(login_sso)
    next_url = request.query_params.get("next") or ""
    if next_url:
        login_sso_url = str(furl(login_sso_url, query_params={"next": next_url}))

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


@app.get("/login/sso/")
def login_sso(request: fastapi.Request):
    if request.user and not request.user.is_anonymous:
        return RedirectResponse(
            safe_next_url(request.query_params, default=DEFAULT_LOGIN_REDIRECT)
        )

    login_url = get_route_path(login)
    next_url = request.query_params.get("next") or ""
    if next_url:
        login_url = str(furl(login_url, query_params={"next": next_url}))

    context = {"request": request, "login_url": login_url}
    return templates.TemplateResponse("login_sso.html", context=context)


async def form_id_token(request: fastapi.Request):
    form = await request.form()
    return form.get("idToken", "")


@app.post("/login/")
def authentication(
    request: fastapi.Request, id_token: bytes = fastapi.Depends(form_id_token)
):
    ## Taken from https://firebase.google.com/docs/auth/admin/manage-cookies#create_session_cookie

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
                safe_next_url(
                    request.query_params,
                    default=DEFAULT_LOGIN_REDIRECT,
                ),
                status_code=303,
            )
        # User did not sign in recently. To guard against ID token theft, require
        # re-authentication.
        return PlainTextResponse(status_code=401, content="Recent sign in required")
    except auth.InvalidIdTokenError:
        return PlainTextResponse(status_code=401, content="Invalid ID token")
    except FirebaseError:
        return PlainTextResponse(
            status_code=401, content="Failed to create a session cookie"
        )


def authenticate_session(session: dict) -> AppUser | None:
    session_cookie = session.get(FIREBASE_SESSION_COOKIE)
    if not session_cookie:
        # Session cookie is unavailable. Check if anonymous user is available.
        anon_uid = session.get(ANONYMOUS_USER_COOKIE, {}).get("uid")
        if anon_uid:
            try:
                anon_user = AppUser.objects.get(uid=anon_uid)
                if anon_user.is_anonymous:
                    return anon_user
            except AppUser.DoesNotExist:
                # Anonymous user was deleted
                session.pop(ANONYMOUS_USER_COOKIE, None)
        # Session cookie is unavailable. Force user to login.
        return None

    user = _verify_session_cookie(session_cookie)
    if not user:
        # Session cookie was invalid
        session.pop(FIREBASE_SESSION_COOKIE, None)
        return None

    return user


def _verify_session_cookie(firebase_cookie: str) -> AppUser | None:
    try:
        decoded_claims = auth.verify_session_cookie(firebase_cookie)
        return AppUser.objects.get_or_create_from_uid(decoded_claims["uid"])[0]
    except (auth.UserNotFoundError, auth.InvalidSessionCookieError):
        # Session cookie is invalid, expired or revoked. Force user to login.
        return None


def init_firebase_anonymous_user(
    request: fastapi.Request | BasePageRequest,
) -> "AppUser":
    uid = auth.create_user().uid
    user = AppUser.objects.create(
        uid=uid,
        is_anonymous=True,
        balance=settings.ANON_USER_FREE_CREDITS,
    )
    if isinstance(request, fastapi.Request):
        request.scope["user"] = user
    elif isinstance(request, BasePageRequest):
        request.user = user
    request.session[ANONYMOUS_USER_COOKIE] = dict(uid=user.uid)
    return user
