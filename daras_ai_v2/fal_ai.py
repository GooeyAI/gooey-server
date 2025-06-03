import json
import typing

import requests
from furl import furl

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
            return r.json()


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
