import base64
import datetime
import typing

import requests

from daras_ai.image_input import storage_blob_for
from daras_ai_v2 import settings


class GpuEndpoints:
    wav2lip = settings.GPU_SERVER_1.copy().set(port=5001)
    glid_3_xl_stable = settings.GPU_SERVER_1.copy().set(port=5002)
    gfpgan = settings.GPU_SERVER_1.copy().set(port=5003)
    dichotomous_image_segmentation = settings.GPU_SERVER_1.copy().set(port=5004)
    # flan_t5 = f"{settings.GPU_SERVER_2}:5005"
    # runway_ml_inpainting = f"{settings.GPU_SERVER_2}:5006"
    u2net = settings.GPU_SERVER_1.copy().set(port=5007)
    # deforum_sd = f"{settings.GPU_SERVER_2}:5008"
    sd_2 = settings.GPU_SERVER_1.copy().set(port=5011)
    sd_multi = settings.GPU_SERVER_1.copy().set(port=5012)
    # real_esrgan = settings.GPU_SERVER_1furl().set(port=5013)
    defourm_sd = settings.GPU_SERVER_1.copy().set(port=5014) / "deforum"

    lavis = settings.GPU_SERVER_1.copy().set(port=5015)
    vqa = lavis / "vqa"
    image_captioning = lavis / "image-captioning"


def call_gpu_server_b64(*, endpoint: str, input_data: dict) -> list[bytes]:
    b64_data = call_gpu_server(endpoint=endpoint, input_data=input_data)
    if not isinstance(b64_data, list):
        b64_data = [b64_data]
    return [b64_img_decode(item) for item in b64_data]


def b64_img_decode(b64_data):
    if not b64_data:
        raise ValueError("Empty Ouput")
    return base64.b64decode(b64_data[b64_data.find(",") + 1 :])


def call_gpu_server(*, endpoint: str, input_data: dict) -> typing.Any:
    r = requests.post(
        f"{endpoint}/predictions",
        json={"input": input_data},
    )
    r.raise_for_status()
    return r.json()["output"]


def call_sd_multi(endpoint: str, pipeline: dict, inputs: dict) -> typing.List[str]:
    prompt = inputs["prompt"]
    num_images_per_prompt = inputs["num_images_per_prompt"]
    num_outputs = len(prompt) * num_images_per_prompt

    blobs = [
        storage_blob_for(f"gooey.ai - {prompt} ({i + 1}).png")
        for i in range(num_outputs)
    ]

    pipeline["upload_urls"] = [
        blob.generate_signed_url(
            version="v4",
            # This URL is valid for 15 minutes
            expiration=datetime.timedelta(minutes=30),
            # Allow PUT requests using this URL.
            method="PUT",
            content_type="image/png",
        )
        for blob in blobs
    ]

    r = requests.post(
        GpuEndpoints.sd_multi + f"/{endpoint}/",
        json={
            "pipeline": pipeline,
            "inputs": inputs,
        },
    )
    r.raise_for_status()

    return [blob.public_url for blob in blobs]
