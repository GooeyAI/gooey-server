import logging
import random
from http.client import HTTPConnection  # py3
from threading import Thread

HTTPConnection.debuglevel = 1

logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)
requests_log = logging.getLogger("requests.packages.urllib3")
requests_log.setLevel(logging.DEBUG)
requests_log.propagate = True

import string

import numpy as np

from daras_ai.image_input import cv2_img_to_bytes
from daras_ai_v2.crypto import get_random_string
from daras_ai_v2.stable_diffusion import (
    controlnet,
    ControlNetModels,
    ImageToImageModels,
    text2img,
    TextToImageModels,
    img2img,
    instruct_pix2pix,
    sd_upscale,
)

random_img = "https://picsum.photos/768"
blank_img_bytes = cv2_img_to_bytes(np.zeros((768, 768, 3), dtype=np.uint8))


# def fn():
#     text2img(
#         selected_model=ImageToImageModels.sd_1_5.name,
#         prompt=get_random_string(100, string.ascii_letters),
#         num_outputs=1,
#         num_inference_steps=1,
#         width=768,
#         height=768,
#         guidance_scale=7,
#     )
#     # r = requests.get(GpuEndpoints.sd_multi / "magic")
#     # raise_for_status(r)
#     # img2img(
#     #     selected_model=ImageToImageModels.sd_1_5.name,
#     #     prompt=get_random_string(100, string.ascii_letters),
#     #     num_outputs=1,
#     #     init_image=random_img,
#     #     init_image_bytes=blank_img_bytes,
#     #     num_inference_steps=1,
#     #     guidance_scale=7,
#     # )
#     # controlnet(
#     #     selected_controlnet_model=ControlNetModels.sd_controlnet_depth.name,
#     #     selected_model=ImageToImageModels.sd_1_5.name,
#     #     prompt=get_random_string(100, string.ascii_letters),
#     #     num_outputs=1,
#     #     init_image=random_img,
#     #     num_inference_steps=1,
#     #     guidance_scale=7,
#     # )
#
#
# while True:
#     for _ in range(1):
#         t = Thread(target=fn)
#         t.start()
#     t.join()
# exit()
tasks = []

for model in ImageToImageModels:
    if model in [
        ImageToImageModels.instruct_pix2pix,
        ImageToImageModels.dall_e,
        ImageToImageModels.jack_qiao,
    ]:
        continue
    print(model)
    tasks.append(
        (
            img2img,
            dict(
                selected_model=model.name,
                prompt=get_random_string(100, string.ascii_letters),
                num_outputs=4,
                num_inference_steps=10,
                init_image=random_img,
                init_image_bytes=blank_img_bytes,
                guidance_scale=7,
            ),
        )
    )
    for controlnet_model in ControlNetModels:
        if model in [
            ImageToImageModels.sd_2,
        ]:
            continue
        print(controlnet_model)
        tasks.append(
            (
                controlnet,
                dict(
                    selected_model=model.name,
                    selected_controlnet_model=controlnet_model.name,
                    prompt=get_random_string(100, string.ascii_letters),
                    num_outputs=4,
                    init_images=random_img,
                    num_inference_steps=1,
                    guidance_scale=7,
                ),
            )
        )

for model in TextToImageModels:
    if model in [
        TextToImageModels.dall_e,
        TextToImageModels.jack_qiao,
    ]:
        continue
    print(model)
    tasks.append(
        (
            text2img,
            dict(
                selected_model=model.name,
                prompt=get_random_string(100, string.ascii_letters),
                num_outputs=4,
                num_inference_steps=10,
                width=768,
                height=768,
                guidance_scale=7,
            ),
        )
    )

tasks.append(
    (
        instruct_pix2pix,
        dict(
            prompt=get_random_string(100, string.ascii_letters),
            num_outputs=4,
            num_inference_steps=10,
            images=[random_img],
            guidance_scale=7,
            image_guidance_scale=2,
        ),
    )
)

tasks.append(
    (
        sd_upscale,
        dict(
            prompt=get_random_string(100, string.ascii_letters),
            num_outputs=1,
            num_inference_steps=1,
            guidance_scale=7,
            image=random_img,
        ),
    )
)


def call(fn, kwargs):
    print(fn.__name__, fn(**kwargs))


random.shuffle(tasks)
for args in tasks:
    Thread(target=call, args=args).start()
