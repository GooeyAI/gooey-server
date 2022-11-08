import base64
import typing

import requests


class GpuEndpoints:
    wav2lip = "http://gpu-1.gooey.ai:5001"
    glid_3_xl_stable = "http://gpu-1.gooey.ai:5002"
    gfpgan = "http://gpu-1.gooey.ai:5003"
    dichotomous_image_segmentation = "http://gpu-1.gooey.ai:5004"

    flan_t5 = "http://gpu-2.gooey.ai:5005"
    runway_ml_inpainting = "http://gpu-2.gooey.ai:5006"


def call_gpu_server_b64(*, endpoint: str, input_data: dict) -> list[bytes]:
    b64_data = call_gpu_server(endpoint=endpoint, input_data=input_data)
    if not isinstance(b64_data, list):
        b64_data = [b64_data]
    return [b64_img_decode(item) for item in b64_data]


def b64_img_decode(b64_data):
    return base64.b64decode(b64_data[b64_data.find(",") + 1 :])


def call_gpu_server(*, endpoint: str, input_data: dict) -> typing.Any:
    r = requests.post(
        f"{endpoint}/predictions",
        json={"input": input_data},
    )
    r.raise_for_status()
    return r.json()["output"]
