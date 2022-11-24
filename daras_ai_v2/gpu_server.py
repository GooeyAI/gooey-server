import base64
import typing

import requests

from daras_ai_v2 import settings


class GpuEndpoints:
    wav2lip = f"{settings.GPU_SERVER_1}:5001"
    glid_3_xl_stable = f"{settings.GPU_SERVER_1}:5002"
    gfpgan = f"{settings.GPU_SERVER_1}:5003"
    dichotomous_image_segmentation = f"{settings.GPU_SERVER_2}:5004"
    flan_t5 = f"{settings.GPU_SERVER_2}:5005"
    runway_ml_inpainting = f"{settings.GPU_SERVER_2}:5006"
    u2net = f"{settings.GPU_SERVER_1}:5007"
    deforum_sd = f"{settings.GPU_SERVER_2}:5008"
    sd_1_5 = f"{settings.GPU_SERVER_2}:5009"
    sd_2 = f"{settings.GPU_SERVER_1}:5011"
    # openjourney = f"{settings.GPU_SERVER_2}:5010"


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
