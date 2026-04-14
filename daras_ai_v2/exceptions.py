from __future__ import annotations

import json
import subprocess
import typing

import requests
from furl import furl
from loguru import logger
from requests import HTTPError
from starlette.status import HTTP_401_UNAUTHORIZED
from starlette.status import HTTP_402_PAYMENT_REQUIRED

from daras_ai_v2 import settings
from daras_ai_v2.fastapi_tricks import get_route_path

if typing.TYPE_CHECKING:
    from app_users.models import AppUser
    from bots.models import SavedRun


def raise_for_status(resp: requests.Response, is_user_url: bool = False):
    """Raises :class:`HTTPError`, if one occurred."""

    http_error_msg = ""
    if isinstance(resp.reason, bytes):
        # We attempt to decode utf-8 first because some servers
        # choose to localize their reason strings. If the string
        # isn't utf-8, we fall back to iso-8859-1 for all other
        # encodings. (See PR #3538)
        try:
            reason = resp.reason.decode("utf-8")
        except UnicodeDecodeError:
            reason = resp.reason.decode("iso-8859-1")
    else:
        reason = resp.reason

    if 400 <= resp.status_code < 500:
        http_error_msg = f"{resp.status_code} Client Error: {reason} | URL: {resp.url} | Response: {_response_preview(resp)!r}"

    elif 500 <= resp.status_code < 600:
        http_error_msg = f"{resp.status_code} Server Error: {reason} | URL: {resp.url} | Response: {_response_preview(resp)!r}"

    if http_error_msg:
        exc = HTTPError(http_error_msg, response=resp)
        if is_user_url:
            raise UserError(
                f"[{resp.status_code}] You have provided an invalid URL: {resp.url} "
                "Please make sure the URL is correct and accessible. ",
            ) from exc
        else:
            raise exc


def _response_preview(resp: requests.Response) -> bytes:
    from daras_ai.image_input import truncate_filename

    return truncate_filename(resp.content, 500, sep=b"...")


class UserError(Exception):
    def __init__(
        self,
        message: str,
        sentry_level: str = "info",
        status_code: int = None,
        error_params: dict | None = None,
    ):
        self.message = message
        self.sentry_level = sentry_level
        self.status_code = status_code
        self.error_params = error_params
        super().__init__(message)


class GPUError(UserError):
    pass


class InsufficientCredits(UserError):
    def __init__(self, *, price: int = 0):
        super().__init__(
            "Insufficient credits",
            status_code=HTTP_402_PAYMENT_REQUIRED,
            error_params={"price": price},
        )

    @staticmethod
    def render(error_params: dict):
        import gooey_gui as gui

        from daras_ai_v2.base import SUBMIT_AFTER_LOGIN_Q
        from routers.account import account_route
        from workspaces.widgets import set_current_workspace

        RERUN_KEY = "--insufficient-credits-rerun"
        UPGRADE_KEY = "--insufficient-credits-upgrade"
        BUY_CREDITS_KEY = "--insufficient-credits-buy-personal"

        request = error_params["request"]
        sr = error_params["sr"]
        current_workspace = error_params.get("current_workspace")
        price = error_params.get("price", None)
        current_user = request.user
        personal_workspace = (
            current_user and current_user.get_or_create_personal_workspace()[0]
        )

        show_upgrade = False

        if (
            not current_user
            or not sr.workspace
            or sr.workspace not in current_user.cached_workspaces
        ):
            # anon user or unrelated user or sr.workspace is None
            title = "Run failed (Not enough credits)"
            rerun_workspace = current_workspace

        elif current_user.uid == sr.uid and len(current_user.cached_workspaces) <= 1:
            # user started the run in their personal workspace
            # AND they are not part of any team workspace
            title = "You've run out of Gooey.AI credits"
            rerun_workspace = personal_workspace

        else:
            # user is part of the run's workspace
            title = f"You've run out of credits in {sr.workspace.display_name(current_user)}"
            rerun_workspace = personal_workspace
            if (
                not sr.workspace.is_personal
                and current_user in sr.workspace.get_admins()
            ):
                show_upgrade = True

        if not rerun_workspace:
            rerun_workspace_name = None
        elif rerun_workspace.is_personal:
            rerun_workspace_name = "Personal"
        else:
            rerun_workspace_name = rerun_workspace.display_name(current_user)

        show_rerun = rerun_workspace and rerun_workspace.balance >= (price or 1)
        is_anonymous = not current_user or current_user.is_anonymous
        account_url = furl(settings.APP_BASE_URL) / get_route_path(account_route)
        if is_anonymous:
            account_url.query.params["next"] = sr.get_app_url(
                query_params={SUBMIT_AFTER_LOGIN_Q: "1"},
            )

        if gui.session_state.pop(RERUN_KEY, None) and rerun_workspace:
            set_current_workspace(request.session, rerun_workspace.id)
            gui.session_state["-submit-workflow"] = True
            raise gui.RerunException()

        if gui.session_state.pop(BUY_CREDITS_KEY, None) and rerun_workspace:
            set_current_workspace(request.session, rerun_workspace.id)
            raise gui.RedirectException(get_route_path(account_route))

        if gui.session_state.pop(UPGRADE_KEY, None) and sr:
            set_current_workspace(request.session, sr.workspace_id)
            raise gui.RedirectException(get_route_path(account_route))

        gui.component(
            "InsufficientCredits",
            accountUrl=str(account_url),
            isAnonymous=is_anonymous,
            verifiedEmailUserFreeCredits=settings.VERIFIED_EMAIL_USER_FREE_CREDITS,
            rerunKey=RERUN_KEY,
            upgradeKey=UPGRADE_KEY,
            buyCreditsKey=BUY_CREDITS_KEY,
            price=price,
            title=title,
            showUpgrade=show_upgrade,
            showRerun=bool(show_rerun),
            rerunWorkspaceBalance=(
                rerun_workspace.balance if rerun_workspace else None
            ),
            rerunWorkspaceName=rerun_workspace_name,
        )


class OneDriveAuth(UserError):
    def __init__(self, auth_url):
        message = f"""
<p>
OneDrive access is currently unavailable. 
</p>

<p>
<a href="{auth_url}">LOGIN</a> to your OneDrive account to enable access to your files.
</p>
"""
        super().__init__(message, status_code=HTTP_401_UNAUTHORIZED)


class ComposioAuthRequired(UserError):
    def __init__(self, redirect_url: str):
        message = f"Access required. Connect your account to continue: {redirect_url}"
        super().__init__(
            message,
            status_code=HTTP_401_UNAUTHORIZED,
            error_params=dict(redirect_url=redirect_url),
        )

    @staticmethod
    def render(error_params: dict | None):
        import gooey_gui as gui

        error_params = error_params or {}
        gui.component(
            "ComposioAuthRequired",
            redirectUrl=error_params.get("redirect_url"),
        )


class PaymentRequired(UserError):
    def __init__(self, paid_only_models: list[str]):
        message = f"Your workspace requested paid-only model access. Please upgrade to use these models: {', '.join(paid_only_models)}"
        super().__init__(
            message,
            status_code=HTTP_402_PAYMENT_REQUIRED,
            error_params=dict(paid_only_models=paid_only_models),
        )

    @staticmethod
    def render(error_params: dict | None):
        import gooey_gui as gui

        error_params = error_params or {}
        gui.component(
            "PaymentRequired",
            discordInviteUrl=settings.DISCORD_INVITE_URL,
            paidOnlyModels=error_params.get("paid_only_models") or [],
        )


FFMPEG_ERR_MSG = (
    "Unsupported File Format\n\n"
    "We encountered an issue processing your file as it appears to be in a format not supported by our system or may be corrupted. "
    "You can find a list of supported formats at [FFmpeg Formats](https://ffmpeg.org/general.html#File-Formats)."
)


def ffmpeg(*args) -> str:
    return call_cmd("ffmpeg", "-hide_banner", "-y", *args, err_msg=FFMPEG_ERR_MSG)


def ffprobe(filename: str) -> dict:
    text = call_cmd(
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_streams",
        filename,
        err_msg=FFMPEG_ERR_MSG,
    )
    return json.loads(text)


def call_cmd(
    *args, err_msg: str = "", ok_returncodes: typing.Iterable[int] = ()
) -> str:
    logger.info("$ " + " ".join(map(str, args)))
    try:
        return subprocess.check_output(args, stderr=subprocess.STDOUT, text=True)
    except subprocess.CalledProcessError as e:
        if e.returncode in ok_returncodes:
            return e.output
        err_msg = err_msg or f"{str(args[0]).capitalize()} Error"
        try:
            raise subprocess.SubprocessError(e.output) from e
        except subprocess.SubprocessError as e:
            raise UserError(err_msg) from e
