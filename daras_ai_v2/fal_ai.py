import json
import mimetypes
import os
import time
import typing
from urllib.parse import urlparse

import requests
from furl import furl
from loguru import logger

from daras_ai.image_input import get_mimetype_from_response, upload_file_from_bytes
from daras_ai_v2 import settings
from daras_ai_v2.exceptions import raise_for_status


def generate_on_fal(model_id: str, payload: dict) -> typing.Generator[str, None, dict]:
    r = requests.post(
        str(furl("https://queue.fal.run") / model_id),
        headers=_fal_auth_headers(),
        json=payload,
    )
    raise_for_status(r)
    result = r.json()

    yield from stream_fal_status_events(result["status_url"])

    r = requests.get(result["response_url"], headers=_fal_auth_headers())
    raise_for_status(r)
    return _rewrite_fal_asset_urls(r.json())


def stream_fal_status_events(
    status_url: str,
    *,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> typing.Iterator[str]:
    stream_url = furl(status_url).add(path="stream", query_params=dict(logs="1")).url

    for attempt in range(max_retries):
        try:
            response = requests.get(
                stream_url, headers=_fal_auth_headers(), stream=True
            )
            raise_for_status(response)
            for event_data in stream_sse_json(response):
                if event_data["status"] == "COMPLETED":
                    return
                logs = event_data["logs"]
                if not logs:
                    continue
                yield "`" + logs[-1]["message"] + "`"
        except requests.exceptions.ChunkedEncodingError:
            if attempt >= max_retries - 1:
                raise
            logger.warning(
                f"ChunkedEncodingError: [{attempt + 1}/{max_retries}] retrying in {retry_delay} seconds"
            )
            time.sleep(retry_delay)
        else:
            return


def stream_sse_json(response: requests.Response) -> typing.Iterator[dict]:
    with response:
        for line in response.iter_lines():
            if not line:
                continue
            decoded_line = line.decode("utf-8")
            if not decoded_line.startswith("data: "):
                continue
            event_data = decoded_line.removeprefix("data: ")
            yield json.loads(event_data)


def _fal_auth_headers():
    return {
        "Authorization": f"Key {settings.FAL_API_KEY}",
        "X-Fal-Object-Lifecycle-Preference": json.dumps(
            {"expiration_duration_seconds": 3600}
        ),
    }


def _rewrite_fal_asset_urls(value: typing.Any) -> typing.Any:
    match value:
        case str() if _is_fal_asset_url(value):
            filename = os.path.basename(urlparse(value).path) or "fal_asset"
            return _reupload_fal_asset_url(value, filename=filename)
        case dict():
            out = {}
            for key, child in value.items():
                out[key] = _rewrite_fal_asset_urls(child)
            return out
        case list():
            return [_rewrite_fal_asset_urls(item) for item in value]
        case _:
            return value


def _is_fal_asset_url(url: str) -> bool:
    try:
        f = furl(url)
    except Exception:
        return False
    return "fal.media" in f.origin


def _reupload_fal_asset_url(url: str, *, filename: str) -> str:
    r = requests.get(url)
    raise_for_status(r)

    content_type = get_mimetype_from_response(r) or None

    # If FAL returns extensionless filenames, preserve a useful extension.
    if (
        not os.path.splitext(filename)[1]
        and content_type
        and (ext := mimetypes.guess_extension(content_type))
    ):
        filename += ext

    try:
        uploaded_url = upload_file_from_bytes(
            filename, r.content, content_type=content_type
        )
    except Exception:
        logger.exception("Failed to re-upload FAL asset URL {}", url)
        return url

    return uploaded_url
