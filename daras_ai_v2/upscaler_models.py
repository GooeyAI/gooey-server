import typing
from enum import Enum
from pathlib import Path

import replicate
import requests

from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.gpu_server import call_celery_task_outfile
from daras_ai_v2.pydantic_validation import FieldHttpUrl
from daras_ai_v2.stable_diffusion import sd_upscale


class UpscalerModel(typing.NamedTuple):
    model_id: str
    label: str
    supports_video: bool = False
    is_bg_model: bool = False


class UpscalerModels(UpscalerModel, Enum):
    gfpgan_1_4 = UpscalerModel(
        model_id="GFPGANv1.4",
        label="GFPGAN v1.4 (Tencent ARC)",
        supports_video=True,
    )
    real_esrgan_x2 = UpscalerModel(
        model_id="RealESRGAN_x2plus",
        label="Real-ESRGAN x2 (xinntao)",
        is_bg_model=True,
    )
    sd_x4 = UpscalerModel(
        model_id="stabilityai/stable-diffusion-x4-upscaler",
        label="Stable Diffusion x4 🔻 (xinntao)",
    )
    real_esrgan = UpscalerModel(
        model_id="nightmareai/real-esrgan",
        label="Real-ESRGAN 🔻 (xinntao)",
    )
    gfpgan = UpscalerModel(
        model_id="tencentarc/gfpgan",
        label="GFPGAN 🔻 (Tencent ARC)",
    )


def run_upscaler_model(
    *,
    image: str = None,
    video: str = None,
    scale: int,
    selected_model: UpscalerModel,
    bg_model: UpscalerModel = None,
    filename: str = None,
) -> FieldHttpUrl:
    match selected_model:
        case UpscalerModels.gfpgan_1_4:
            if video:
                ext = "mp4"
            else:
                ext = "png"
            return call_celery_task_outfile(
                "gfpgan",
                pipeline=dict(
                    model_id=selected_model.model_id,
                    bg_model_id=bg_model.model_id if bg_model else None,
                ),
                inputs=dict(input=image, video=video, scale=scale),
                content_type=None,  # inferred by the gpu
                filename=filename
                or f"gooey.ai restoration - {Path(video or image).stem}.{ext}",
            )[0]
        case UpscalerModels.sd_x4:
            return sd_upscale(
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
        case UpscalerModels.real_esrgan:
            img_bytes = _real_esrgan(image, scale, face_enhance=False)
            return upload_file_from_bytes(
                filename or f"gooey.ai upscaled - {Path(image).stem}.png", img_bytes
            )
        case UpscalerModels.gfpgan:
            img_bytes = _real_esrgan(image, scale, face_enhance=True)
            return upload_file_from_bytes(
                filename or f"gooey.ai upscaled - {Path(image).stem}.png", img_bytes
            )
        case _:
            raise UserError(f"Unkown upscaler: {selected_model}")


def _real_esrgan(img: str, scale: int, face_enhance: bool) -> bytes:
    # https://replicate.com/nightmareai/real-esrgan/versions/42fed1c4974146d4d2414e2be2c5277c7fcf05fcc3a73abf41610695738c1d7b#output-schema
    model = replicate.models.get(UpscalerModels.real_esrgan.model_id)
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
    model = replicate.models.get(UpscalerModels.gfpgan.model_id)
    version = model.versions.get(
        "9283608cc6b7be6b65a8e44983db012355fde4132009bf99d976b2f0896856a3"
    )
    img = version.predict(img=img, version="v1.4", scale=scale)
    return requests.get(img).content
