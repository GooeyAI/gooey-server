import json
import subprocess
import typing

import requests
from furl import furl
from loguru import logger
from requests import HTTPError
from starlette.status import HTTP_402_PAYMENT_REQUIRED

from daras_ai_v2 import settings

if typing.TYPE_CHECKING:
    from bots.models import SavedRun
    from bots.models import AppUser


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
        self, message: str, sentry_level: str = "info", status_code: int = None
    ):
        self.message = message
        self.sentry_level = sentry_level
        self.status_code = status_code
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
            # language=HTML
            message = f"""
<p data-{SUBMIT_AFTER_LOGIN_Q}>
Doh! <a href="{account_url}" target="_top">Please login</a> to run more Gooey.AI workflows.
</p>

You’ll receive {settings.LOGIN_USER_FREE_CREDITS} Credits when you sign up via your phone #, Google, Apple or GitHub account
and can <a href="/pricing/" target="_blank">purchase more</a> for $1/100 Credits.
"""
        else:
            # language=HTML
            message = f"""
<p>
Doh! You’re out of Gooey.AI credits.
</p>

<p>
Please <a href="{account_url}" target="_blank">buy more</a> to run more workflows.
</p>

We’re always on <a href="{settings.DISCORD_INVITE_URL}" target="_blank">discord</a> if you’ve got any questions.
"""

        super().__init__(message, status_code=HTTP_402_PAYMENT_REQUIRED)


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
