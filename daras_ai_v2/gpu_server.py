import base64
import datetime
import os
import typing

import requests
from furl import furl

from daras_ai.image_input import storage_blob_for
from daras_ai_v2 import settings


class GpuEndpoints:
    glid_3_xl_stable = settings.GPU_SERVER_1.copy().set(port=5002)
    deepfloyd_if = settings.GPU_SERVER_1.copy().set(port=5018) / "deepfloyd_if"
    sd_2 = settings.GPU_SERVER_1.copy().set(port=5011)


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


def call_sd_multi(
    endpoint: str,
    pipeline: dict,
    inputs: dict,
) -> typing.List[str]:
    prompt = inputs["prompt"]
    num_images_per_prompt = inputs["num_images_per_prompt"]
    num_outputs = len(prompt) * num_images_per_prompt
    # sd
    if not isinstance(pipeline["model_id"], list):
        return call_celery_task_outfile(
            endpoint,
            pipeline=pipeline,
            inputs=inputs,
            content_type="image/png",
            filename=f"gooey.ai - {prompt}.png",
            num_outputs=num_outputs,
        )

    # deepfloyd
    base = GpuEndpoints.deepfloyd_if
    inputs["num_inference_steps"] = [inputs["num_inference_steps"], 50, 75]
    inputs["guidance_scale"] = [inputs["guidance_scale"], 4, 9]
    return call_gooey_gpu(
        endpoint=base / "/text2img/",
        content_type="image/png",
        pipeline=pipeline,
        inputs=inputs,
        num_outputs=num_outputs,
        filename=prompt,
    )


def call_gooey_gpu(
    *,
    endpoint: furl,
    content_type: str,
    pipeline: dict,
    inputs: dict,
    filename: str,
    num_outputs: int = 1,
) -> list[str]:
    blobs = [
        storage_blob_for(f"gooey.ai - {filename} ({i + 1}).png")
        for i in range(num_outputs)
    ]
    pipeline["upload_urls"] = [
        blob.generate_signed_url(
            version="v4",
            # This URL is valid for 15 minutes
            expiration=datetime.timedelta(hours=12),
            # Allow PUT requests using this URL.
            method="PUT",
            content_type=content_type,
        )
        for blob in blobs
    ]
    r = requests.post(
        str(endpoint),
        json={"pipeline": pipeline, "inputs": inputs},
    )
    r.raise_for_status()
    return [blob.public_url for blob in blobs]


def call_celery_task_outfile(
    task_name: str,
    *,
    pipeline: dict,
    inputs: dict,
    content_type: str,
    filename: str,
    num_outputs: int = 1,
):
    blobs = [storage_blob_for(filename) for i in range(num_outputs)]
    pipeline["upload_urls"] = [
        blob.generate_signed_url(
            version="v4",
            # This URL is valid for 15 minutes
            expiration=datetime.timedelta(hours=12),
            # Allow PUT requests using this URL.
            method="PUT",
            content_type=content_type,
        )
        for blob in blobs
    ]
    call_celery_task(task_name, pipeline=pipeline, inputs=inputs)
    return [blob.public_url for blob in blobs]


_app = None


def get_celery():
    global _app
    if _app is None:
        from celery import Celery

        _app = Celery()
        _app.conf.broker_url = settings.GPU_CELERY_BROKER_URL
        _app.conf.result_backend = settings.GPU_CELERY_RESULT_BACKEND

    return _app


def call_celery_task(
    task_name: str,
    *,
    pipeline: dict,
    inputs: dict,
    queue_prefix: str = "gooey-gpu",
):
    queue = os.path.join(queue_prefix, pipeline["model_id"].strip()).strip("/")
    result = get_celery().send_task(
        task_name, kwargs=dict(pipeline=pipeline, inputs=inputs), queue=queue
    )
    return result.get(disable_sync_subtasks=False)
