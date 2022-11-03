import base64
import typing

import requests

# GPU_API_ROOT = "http://gpu-1.gooey.ai"
GPU_API_ROOT = "http://gooey-a-1"


def call_gpu_server_b64(port: int, input_data: dict) -> list[bytes]:
    b64_data = call_gpu_server(port, input_data)
    if not isinstance(b64_data, list):
        b64_data = [b64_data]
    return [_b64_decode(item) for item in b64_data]


def _b64_decode(b64_data):
    return base64.b64decode(b64_data[b64_data.find(",") + 1 :])


def call_gpu_server(port: int, input_data: dict) -> typing.Any:
    r = requests.post(
        f"{GPU_API_ROOT}:{port}/predictions",
        json={"input": input_data},
    )
    r.raise_for_status()
    b64_data = r.json()["output"]
    return b64_data
