import json
import mimetypes
import os
import typing
from urllib.parse import urlparse

import requests
from furl import furl
from loguru import logger

from daras_ai.image_input import upload_file_from_bytes
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

    status_url = (
        furl(result["status_url"]).add(path="stream", query_params=dict(logs="1")).url
    )

    for event_data in stream_sse_json(
        requests.get(status_url, headers=_fal_auth_headers(), stream=True)
    ):
        if event_data["status"] != "COMPLETED":
            logs = event_data["logs"]
            if not logs:
                continue
            yield "`" + logs[-1]["message"] + "`"
        else:
            repsonse_url = event_data["response_url"]
            r = requests.get(repsonse_url, headers=_fal_auth_headers())
            raise_for_status(r)
            return _rewrite_fal_asset_urls(r.json())


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
    return {"Authorization": f"Key {settings.FAL_API_KEY}"}


def _rewrite_fal_asset_urls(
    value: typing.Any,
    *,
    parent_key: str | None = None,
    url_cache: dict[str, str] | None = None,
) -> typing.Any:
    if url_cache is None:
        url_cache = {}

    match value:
        case dict():
            out = {}
            for key, child in value.items():
                out[key] = _rewrite_fal_asset_urls(
                    child,
                    parent_key=key,
                    url_cache=url_cache,
                )

            asset_url = out.get("url")
            if isinstance(asset_url, str) and _is_fal_asset_url(asset_url):
                out["url"] = _reupload_fal_asset_url(
                    asset_url,
                    preferred_filename=out.get("file_name")
                    or out.get("filename")
                    or _default_filename_for_fal_asset(parent_key, out),
                    url_cache=url_cache,
                )
            return out
        case list():
            return [
                _rewrite_fal_asset_urls(
                    item, parent_key=parent_key, url_cache=url_cache
                )
                for item in value
            ]
        case _:
            return value


def _is_fal_asset_url(url: str) -> bool:
    try:
        f = furl(url)
    except Exception:
        return False
    host = (f.host or "").lower()
    return host.endswith("fal.media")


def _default_filename_for_fal_asset(parent_key: str | None, payload: dict) -> str:
    stem = (parent_key or "fal_asset").strip() or "fal_asset"
    content_type = payload.get("content_type") or payload.get("mime_type") or ""
    ext = mimetypes.guess_extension(content_type) or ""
    return f"{stem}{ext}"


def _reupload_fal_asset_url(
    url: str,
    *,
    preferred_filename: str | None,
    url_cache: dict[str, str],
) -> str:
    cached = url_cache.get(url)
    if cached:
        return cached

    r = requests.get(url)
    raise_for_status(r)

    filename = preferred_filename or os.path.basename(urlparse(url).path) or "fal_asset"
    content_type = r.headers.get("Content-Type", "").split(";")[0] or None

    # If FAL returns extensionless filenames, preserve a useful extension.
    if not os.path.splitext(filename)[1] and content_type:
        if ext := mimetypes.guess_extension(content_type):
            filename += ext

    try:
        uploaded_url = upload_file_from_bytes(filename, r.content, content_type)
    except Exception:
        logger.exception("Failed to re-upload FAL asset URL {}", url)
        return url

    url_cache[url] = uploaded_url
    return uploaded_url
