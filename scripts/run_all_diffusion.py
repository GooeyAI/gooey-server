import logging
import contextlib
from asyncio import sleep
from http.client import HTTPConnection  # py3
from threading import Thread

import requests

from daras_ai_v2.gpu_server import GpuEndpoints

HTTPConnection.debuglevel = 1

logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)
requests_log = logging.getLogger("requests.packages.urllib3")
requests_log.setLevel(logging.DEBUG)
requests_log.propagate = True

import os
import string

import numpy as np

from daras_ai.image_input import cv2_img_to_bytes
from daras_ai_v2.crypto import get_random_string
from daras_ai_v2.stable_diffusion import (
    controlnet,
    ControlNetModels,
    Img2ImgModels,
    text2img,
    Text2ImgModels,
    img2img,
    instruct_pix2pix,
    sd_upscale,
)

random_img = "https://picsum.photos/768"
blank_img_bytes = cv2_img_to_bytes(np.zeros((768, 768, 3), dtype=np.uint8))


# def fn():
#     text2img(
#         selected_model=Img2ImgModels.sd_1_5.name,
#         prompt=get_random_string(100, string.ascii_letters),
#         num_outputs=1,
#         num_inference_steps=1,
#         width=768,
#         height=768,
#         guidance_scale=7,
#     )
#     # r = requests.get(GpuEndpoints.sd_multi / "magic")
#     # r.raise_for_status()
#     # img2img(
#     #     selected_model=Img2ImgModels.sd_1_5.name,
#     #     prompt=get_random_string(100, string.ascii_letters),
#     #     num_outputs=1,
#     #     init_image=random_img,
#     #     init_image_bytes=blank_img_bytes,
#     #     num_inference_steps=1,
#     #     guidance_scale=7,
#     # )
#     # controlnet(
#     #     selected_controlnet_model=ControlNetModels.sd_controlnet_depth.name,
#     #     selected_model=Img2ImgModels.sd_1_5.name,
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

for model in Img2ImgModels:
    if model in [
        Img2ImgModels.instruct_pix2pix,
        Img2ImgModels.dall_e,
        Img2ImgModels.jack_qiao,
    ]:
        continue
    print(model)
    img2img(
        selected_model=model.name,
        prompt=get_random_string(100, string.ascii_letters),
        num_outputs=4,
        num_inference_steps=10,
        init_image=random_img,
        init_image_bytes=blank_img_bytes,
        guidance_scale=7,
    )
    for controlnet_model in ControlNetModels:
        if model in [
            Img2ImgModels.sd_2,
        ]:
            continue
        print(controlnet_model)
        controlnet(
            selected_model=model.name,
            selected_controlnet_model=controlnet_model.name,
            prompt=get_random_string(100, string.ascii_letters),
            num_outputs=4,
            init_image=random_img,
            num_inference_steps=1,
            guidance_scale=7,
        )

for model in Text2ImgModels:
    if model in [
        Text2ImgModels.dall_e,
        Text2ImgModels.jack_qiao,
    ]:
        continue
    print(model)
    text2img(
        selected_model=model.name,
        prompt=get_random_string(100, string.ascii_letters),
        num_outputs=4,
        num_inference_steps=1,
        width=768,
        height=768,
        guidance_scale=7,
    )


instruct_pix2pix(
    prompt=get_random_string(100, string.ascii_letters),
    num_outputs=4,
    num_inference_steps=10,
    images=[random_img],
    guidance_scale=7,
    image_guidance_scale=2,
)
sd_upscale(
    prompt=get_random_string(100, string.ascii_letters),
    num_outputs=1,
    num_inference_steps=1,
    guidance_scale=7,
    image=random_img,
)
