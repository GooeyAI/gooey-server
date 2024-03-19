import json
import subprocess

import requests
from loguru import logger
from requests import HTTPError


def raise_for_status(resp: requests.Response):
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
        raise HTTPError(http_error_msg, response=resp)


def _response_preview(resp: requests.Response) -> bytes:
    from daras_ai.image_input import truncate_filename

    return truncate_filename(resp.content, 500, sep=b"...")


class UserError(Exception):
    def __init__(self, message: str, sentry_level: str = "info"):
        self.message = message
        self.sentry_level = sentry_level
        super().__init__(message)


class GPUError(UserError):
    pass


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


def call_cmd(*args, err_msg: str = "") -> str:
    logger.info("$ " + " ".join(map(str, args)))
    try:
        return subprocess.check_output(args, stderr=subprocess.STDOUT, text=True)
    except subprocess.CalledProcessError as e:
        err_msg = err_msg or f"{str(args[0]).capitalize()} Error"
        try:
            raise subprocess.SubprocessError(e.output) from e
        except subprocess.SubprocessError as e:
            raise UserError(err_msg) from e
