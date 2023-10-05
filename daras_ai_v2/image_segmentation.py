from enum import Enum

import requests

from daras_ai_v2.gpu_server import (
    call_celery_task_outfile,
)


class ImageSegmentationModels(Enum):
    dis = "Dichotomous Image Segmentation"
    u2net = "U²-Net"


def u2net(input_image: str) -> bytes:
    url = call_celery_task_outfile(
        "u2net",
        pipeline=dict(model_id="u2net"),
        inputs=[input_image],
        content_type="image/png",
        filename="u2net.png",
    )[0]
    r = requests.get(url)
    r.raise_for_status()
    return r.content


def dis(input_image: str) -> bytes:
    url = call_celery_task_outfile(
        "dis",
        pipeline=dict(model_id="isnet-general-use.pth"),
        inputs=[input_image],
        content_type="image/png",
        filename="dis.png",
    )[0]
    r = requests.get(url)
    r.raise_for_status()
    return r.content
