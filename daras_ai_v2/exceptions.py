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
    def __init__(self, user: "AppUser", sr: "SavedRun"):
        from daras_ai_v2.base import SUBMIT_AFTER_LOGIN_Q

        account_url = furl(settings.APP_BASE_URL) / "account/"
        if user.is_anonymous:
            account_url.query.params["next"] = sr.get_app_url(
                query_params={SUBMIT_AFTER_LOGIN_Q: "1"},
            )
        error_params = dict(
            account_url=str(account_url),
            is_anonymous=user.is_anonymous,
            SUBMIT_AFTER_LOGIN_Q=SUBMIT_AFTER_LOGIN_Q,
        )
        super().__init__(
            "Insufficient credits",
            status_code=HTTP_402_PAYMENT_REQUIRED,
            error_params=error_params,
        )

    @staticmethod
    def render(error_params: dict | None) -> str:
        from daras_ai_v2.settings import templates

        return templates.get_template("insufficient_credits.html").render(
            **(error_params or {})
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
    def render(error_params: dict | None) -> str:
        from daras_ai_v2.settings import templates

        return templates.get_template("composio_auth_required.html").render(
            **(error_params or {})
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
