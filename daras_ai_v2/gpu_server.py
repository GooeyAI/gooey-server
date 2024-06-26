import base64
import datetime
import os
import typing
from time import time

from daras_ai.image_input import storage_blob_for
from daras_ai_v2 import settings
from daras_ai_v2.exceptions import GPUError
from gooeysite.bg_db_conn import get_celery_result_db_safe


def b64_img_decode(b64_data):
    if not b64_data:
        raise ValueError("Empty Ouput")
    return base64.b64decode(b64_data[b64_data.find(",") + 1 :])


def call_sd_multi(
    endpoint: str,
    pipeline: dict,
    inputs: dict,
) -> typing.List[str]:
    prompt = inputs["prompt"]
    num_images_per_prompt = inputs["num_images_per_prompt"]
    num_outputs = len(prompt) * num_images_per_prompt
    return call_celery_task_outfile(
        endpoint,
        pipeline=pipeline,
        inputs=inputs,
        content_type="image/png",
        filename=f"gooey.ai - {prompt}.png",
        num_outputs=num_outputs,
    )


def call_celery_task_outfile(
    task_name: str,
    *,
    pipeline: dict,
    inputs: dict,
    content_type: str | None,
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
        _app.conf.result_extended = True

    return _app


def call_celery_task(
    task_name: str,
    *,
    pipeline: dict,
    inputs: dict,
    queue_prefix: str = "gooey-gpu",
):
    from usage_costs.cost_utils import record_cost_auto
    from usage_costs.models import ModelSku

    queue = build_queue_name(queue_prefix, pipeline["model_id"])
    result = get_celery().send_task(
        task_name, kwargs=dict(pipeline=pipeline, inputs=inputs), queue=queue
    )
    s = time()
    ret = get_celery_result_db_safe(result, propagate=False)
    try:
        result.maybe_throw()
    except Exception as e:
        raise GPUError(f"Error in GPU Task {queue}:{task_name} - {e}") from e
    record_cost_auto(
        model=queue, sku=ModelSku.gpu_ms, quantity=int((time() - s) * 1000)
    )
    return ret


def build_queue_name(queue_prefix: str, model_id: str) -> str:
    return os.path.join(queue_prefix, model_id.strip()).strip("/")
