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

random_img = "https://picsum.photos/512"
blank_img_bytes = cv2_img_to_bytes(np.zeros((768, 768, 3), dtype=np.uint8))

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
        prompt=get_random_string(1024, string.ascii_letters),
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
            prompt=get_random_string(1024, string.ascii_letters),
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
        prompt=get_random_string(1024, string.ascii_letters),
        num_outputs=4,
        num_inference_steps=1,
        width=768,
        height=768,
        guidance_scale=7,
    )

sd_upscale(
    prompt=get_random_string(1024, string.ascii_letters),
    num_outputs=4,
    num_inference_steps=1,
    guidance_scale=7,
    image=random_img,
)

instruct_pix2pix(
    prompt=get_random_string(1024, string.ascii_letters),
    num_outputs=4,
    num_inference_steps=10,
    images=[random_img],
    guidance_scale=7,
    image_guidance_scale=2,
)
