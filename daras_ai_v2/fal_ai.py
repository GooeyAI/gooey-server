import json
import time
import typing

import requests
from furl import furl
from loguru import logger

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
    return r.json()


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
    return {"Authorization": f"Key {settings.FAL_API_KEY}"}
