from logging import getLogger

import requests
from requests import HTTPError

from daras_ai.image_input import truncate_filename

logger = getLogger(__name__)


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
    return truncate_filename(resp.content, 500, sep=b"...")
