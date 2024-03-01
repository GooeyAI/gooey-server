from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from pathlib import Path

import replicate
import requests

from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.gpu_server import call_gpu_server_b64, GpuEndpoints
from daras_ai_v2.stable_diffusion import sd_upscale


class UpscalerModels(Enum):
    sd_x4 = "SD x4 latent upscaler (stability.ai)"
    real_esrgan = "Real-ESRGAN (xinntao)"
    gfpgan = "GFPGAN face restoration (Tencent ARC)"


def run_upscaler_model(
    *,
    image: str,
    scale: int,
    selected_model: str,
    filename: str = None,
) -> str:
    if not filename:
        filename = f"gooey.ai upscaled - {Path(image).stem}.png"

    match selected_model:
        case UpscalerModels.sd_x4.name:
            img = sd_upscale(
                num_outputs=1,
                num_inference_steps=10,
                prompt="",
                # negative_prompt=None,
                guidance_scale=7.5,
                # seed=42,
                # prompt=request.text_prompt,
                # negative_prompt=request.negative_prompt,
                # guidance_scale=request.guidance_scale,
                # seed=request.seed,
                image=image,
            )[0]
        case UpscalerModels.real_esrgan.name:
            img_bytes = _real_esrgan(image, scale, face_enhance=False)
            img = upload_file_from_bytes(filename, img_bytes)
        case UpscalerModels.gfpgan.name:
            img_bytes = _real_esrgan(image, scale, face_enhance=True)
            img = upload_file_from_bytes(filename, img_bytes)
        case _:
            raise UserError(f"Unkown upscaler: {selected_model}")

    return img


def _real_esrgan(img: str, scale: int, face_enhance: bool) -> bytes:
    # https://replicate.com/nightmareai/real-esrgan/versions/42fed1c4974146d4d2414e2be2c5277c7fcf05fcc3a73abf41610695738c1d7b#output-schema
    model = replicate.models.get("nightmareai/real-esrgan")
    version = model.versions.get(
        "42fed1c4974146d4d2414e2be2c5277c7fcf05fcc3a73abf41610695738c1d7b"
    )
    img = version.predict(
        image=img,
        scale=scale,
        face_enhance=face_enhance,
    )
    return requests.get(img).content


def gfpgan(img: str, scale: int = 1) -> bytes:
    # one weird hack to fix the gfpgan's crappy maths -
    #   https://github.com/TencentARC/GFPGAN/blob/2eac2033893ca7f427f4035d80fe95b92649ac56/cog_predict.py#L135
    if scale == 1:
        scale = 2 - 1e-10
    elif scale != 2:
        scale *= 2

    # https://replicate.com/nightmareai/real-esrgan/versions/42fed1c4974146d4d2414e2be2c5277c7fcf05fcc3a73abf41610695738c1d7b#output-schema
    model = replicate.models.get("tencentarc/gfpgan")
    version = model.versions.get(
        "9283608cc6b7be6b65a8e44983db012355fde4132009bf99d976b2f0896856a3"
    )
    img = version.predict(img=img, version="v1.4", scale=scale)
    return requests.get(img).content
