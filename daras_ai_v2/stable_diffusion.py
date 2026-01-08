import io
import typing
from enum import Enum

import openai
import requests
from PIL import Image
from django.db import models
from pydantic import BaseModel

from daras_ai.image_input import (
    bytes_to_cv2_img,
    get_downscale_factor,
    resize_img_fit,
    resize_img_pad,
    upload_file_from_bytes,
)
from daras_ai_v2.exceptions import UserError, raise_for_status
from daras_ai_v2.extract_face import rgb_img_to_rgba
from daras_ai_v2.fal_ai import generate_on_fal
from daras_ai_v2.gpu_server import b64_img_decode, call_sd_multi
from daras_ai_v2.safety_checker import capture_openai_content_policy_violation

SD_IMG_MAX_SIZE = (768, 768)


class InpaintingModels(Enum):
    sd_2 = "Stable Diffusion v2.1 (stability.ai)"
    runway_ml = "Stable Diffusion v1.5 (RunwayML)"
    dall_e = "Dall-E (OpenAI)"

    jack_qiao = "Stable Diffusion v1.4 [Deprecated] (Jack Qiao)"

    @classmethod
    def _deprecated(cls):
        return {cls.jack_qiao}


inpaint_model_ids = {
    InpaintingModels.sd_2: "stabilityai/stable-diffusion-2-inpainting",
    InpaintingModels.runway_ml: "runwayml/stable-diffusion-inpainting",
}


class Text2ImgModels(Enum):
    nano_banana_pro = "Nano Banana Pro (Google)"
    nano_banana = "Nano Banana (Google)"

    flux_1_dev = "FLUX.1 [dev]"

    gpt_image_1 = "GPT Image 1 (OpenAI)"
    gpt_image_1_5 = "GPT Image 1.5 (OpenAI)"
    dall_e_3 = "DALL·E 3 (OpenAI)"
    dall_e = "DALL·E 2 (OpenAI)"

    # sd_1_4 = "SD v1.4 (RunwayML)" # Host this too?
    dream_shaper = "DreamShaper (Lykon)"
    dreamlike_2 = "Dreamlike Photoreal 2.0 (dreamlike.art)"
    sd_2 = "Stable Diffusion v2.1 (stability.ai)"
    sd_1_5 = "Stable Diffusion v1.5 (RunwayML)"

    openjourney_2 = "Open Journey v2 beta [Deprecated] (PromptHero)"
    openjourney = "Open Journey [Deprecated] (PromptHero)"
    analog_diffusion = "Analog Diffusion [Deprecated] (wavymulder)"
    protogen_5_3 = "Protogen v5.3 [Deprecated] (darkstorm2150)"
    jack_qiao = "Stable Diffusion v1.4 [Deprecated] (Jack Qiao)"
    rodent_diffusion_1_5 = "Rodent Diffusion 1.5 [Deprecated] (NerdyRodent)"
    deepfloyd_if = "DeepFloyd IF [Deprecated] (stability.ai)"

    @classmethod
    def _available(cls):
        return set(cls) - cls._deprecated()

    @classmethod
    def _deprecated(cls):
        return {
            cls.jack_qiao,
            cls.deepfloyd_if,
            cls.rodent_diffusion_1_5,
            cls.analog_diffusion,
            cls.openjourney_2,
            cls.openjourney,
            cls.protogen_5_3,
            cls.gpt_image_1,
        }


text2img_model_ids = {
    Text2ImgModels.nano_banana_pro: "fal-ai/nano-banana-pro",
    Text2ImgModels.nano_banana: "fal-ai/nano-banana",
    Text2ImgModels.gpt_image_1: "gpt-image-1",
    Text2ImgModels.gpt_image_1_5: "gpt-image-1.5",
    Text2ImgModels.dall_e_3: "dall-e-3",
    Text2ImgModels.dall_e: "dall-e-2",
    Text2ImgModels.flux_1_dev: "fal-ai/flux-general",
    Text2ImgModels.sd_1_5: "runwayml/stable-diffusion-v1-5",
    Text2ImgModels.sd_2: "stabilityai/stable-diffusion-2-1",
    Text2ImgModels.dream_shaper: "Lykon/DreamShaper",
    Text2ImgModels.dreamlike_2: "dreamlike-art/dreamlike-photoreal-2.0",
}


class Img2ImgModels(Enum):
    nano_banana_pro = "Nano Banana Pro (Google)"
    nano_banana = "Nano Banana (Google)"

    flux_pro_kontext = "FLUX.1 Pro Kontext (fal.ai)"

    gpt_image_1 = "GPT Image 1 (OpenAI)"
    gpt_image_1_5 = "GPT Image 1.5 (OpenAI)"

    instruct_pix2pix = "✨ InstructPix2Pix (Tim Brooks)"

    dream_shaper = "DreamShaper (Lykon)"
    dreamlike_2 = "Dreamlike Photoreal 2.0 (dreamlike.art)"
    sd_2 = "Stable Diffusion v2.1 (stability.ai)"
    sd_1_5 = "Stable Diffusion v1.5 (RunwayML)"

    dall_e = "Dall-E (OpenAI)"

    openjourney_2 = "Open Journey v2 beta [Deprecated] (PromptHero)"
    openjourney = "Open Journey [Deprecated] (PromptHero)"
    analog_diffusion = "Analog Diffusion [Deprecated] (wavymulder)"
    protogen_5_3 = "Protogen v5.3 [Deprecated] (darkstorm2150)"
    jack_qiao = "Stable Diffusion v1.4 [Deprecated] (Jack Qiao)"
    rodent_diffusion_1_5 = "Rodent Diffusion 1.5 [Deprecated] (NerdyRodent)"

    @classmethod
    def _deprecated(cls):
        return {
            cls.jack_qiao,
            cls.rodent_diffusion_1_5,
            cls.openjourney_2,
            cls.openjourney,
            cls.analog_diffusion,
            cls.protogen_5_3,
            cls.dall_e,
            cls.gpt_image_1,
        }

    @classmethod
    def _multi_image_models(cls):
        return {
            cls.nano_banana,
            cls.nano_banana_pro,
            cls.gpt_image_1,
            cls.gpt_image_1_5,
        }


img2img_model_ids = {
    Img2ImgModels.flux_pro_kontext: "fal-ai/flux-pro/kontext",
    Img2ImgModels.sd_2: "stabilityai/stable-diffusion-2-1",
    Img2ImgModels.sd_1_5: "runwayml/stable-diffusion-v1-5",
    Img2ImgModels.dream_shaper: "Lykon/DreamShaper",
    Img2ImgModels.dreamlike_2: "dreamlike-art/dreamlike-photoreal-2.0",
    Img2ImgModels.dall_e: "dall-e-2",
    Img2ImgModels.gpt_image_1: "gpt-image-1",
    Img2ImgModels.gpt_image_1_5: "gpt-image-1.5",
    Img2ImgModels.nano_banana: "fal-ai/nano-banana/edit",
    Img2ImgModels.nano_banana_pro: "fal-ai/nano-banana-pro/edit",
}


class ControlNetModels(Enum):
    sd_controlnet_canny = "Canny"
    sd_controlnet_depth = "Depth"
    sd_controlnet_hed = "HED Boundary"
    sd_controlnet_mlsd = "M-LSD Straight Line"
    sd_controlnet_normal = "Normal Map"
    sd_controlnet_openpose = "Human Pose"
    sd_controlnet_scribble = "Scribble"
    sd_controlnet_seg = "Image Segmentation"
    sd_controlnet_tile = "Tiling"
    sd_controlnet_brightness = "Brightness"
    control_v1p_sd15_qrcode_monster_v2 = "QR Monster V2"


controlnet_model_explanations = {
    ControlNetModels.sd_controlnet_canny: "Canny edge detection",
    ControlNetModels.sd_controlnet_depth: "Depth estimation",
    ControlNetModels.sd_controlnet_hed: "HED edge detection",
    ControlNetModels.sd_controlnet_mlsd: "M-LSD straight line detection",
    ControlNetModels.sd_controlnet_normal: "Normal map estimation",
    ControlNetModels.sd_controlnet_openpose: "Human pose estimation",
    ControlNetModels.sd_controlnet_scribble: "Scribble",
    ControlNetModels.sd_controlnet_seg: "Image segmentation",
    ControlNetModels.sd_controlnet_tile: "Tiling: to preserve small details",
    ControlNetModels.sd_controlnet_brightness: "Brightness: to increase contrast naturally",
    ControlNetModels.control_v1p_sd15_qrcode_monster_v2: "QR Monster: make beautiful QR codes that still scan with a controlnet specifically trained for this purpose",
}

controlnet_model_ids = {
    ControlNetModels.sd_controlnet_canny: "lllyasviel/sd-controlnet-canny",
    ControlNetModels.sd_controlnet_depth: "lllyasviel/sd-controlnet-depth",
    ControlNetModels.sd_controlnet_hed: "lllyasviel/sd-controlnet-hed",
    ControlNetModels.sd_controlnet_mlsd: "lllyasviel/sd-controlnet-mlsd",
    ControlNetModels.sd_controlnet_normal: "lllyasviel/sd-controlnet-normal",
    ControlNetModels.sd_controlnet_openpose: "lllyasviel/sd-controlnet-openpose",
    ControlNetModels.sd_controlnet_scribble: "lllyasviel/sd-controlnet-scribble",
    ControlNetModels.sd_controlnet_seg: "lllyasviel/sd-controlnet-seg",
    ControlNetModels.sd_controlnet_tile: "lllyasviel/control_v11f1e_sd15_tile",
    ControlNetModels.sd_controlnet_brightness: "ioclab/control_v1p_sd15_brightness",
    ControlNetModels.control_v1p_sd15_qrcode_monster_v2: "monster-labs/control_v1p_sd15_qrcode_monster/v2",
}


class Schedulers(models.TextChoices):
    singlestep_dpm_solver = (
        "DPM",
        "DPMSolverSinglestepScheduler",
    )
    multistep_dpm_solver = "DPM Multistep", "DPMSolverMultistepScheduler"
    dpm_sde = (
        "DPM SDE",
        "DPMSolverSDEScheduler",
    )
    dpm_discrete = (
        "DPM Discrete",
        "KDPM2DiscreteScheduler",
    )
    dpm_discrete_ancestral = (
        "DPM Anscetral",
        "KDPM2AncestralDiscreteScheduler",
    )
    unipc = "UniPC", "UniPCMultistepScheduler"
    lms_discrete = (
        "LMS",
        "LMSDiscreteScheduler",
    )
    heun = (
        "Heun",
        "HeunDiscreteScheduler",
    )
    euler = "Euler", "EulerDiscreteScheduler"
    euler_ancestral = (
        "Euler ancestral",
        "EulerAncestralDiscreteScheduler",
    )
    pndm = "PNDM", "PNDMScheduler"
    ddpm = "DDPM", "DDPMScheduler"
    ddim = "DDIM", "DDIMScheduler"
    deis = (
        "DEIS",
        "DEISMultistepScheduler",
    )


class LoraWeight(BaseModel):
    path: str
    scale: float = 1.0


def sd_upscale(
    *,
    prompt: str,
    num_outputs: int,
    image: str,
    num_inference_steps: int,
    negative_prompt: str = None,
    guidance_scale: float,
    seed: int = 42,
):
    from daras_ai_v2.upscaler_models import UpscalerModels

    return call_sd_multi(
        "diffusion.upscale",
        pipeline={
            "model_id": UpscalerModels.sd_x4.model_id,
            # "scheduler": "UniPCMultistepScheduler",
            "disable_safety_checker": True,
            "seed": seed,
        },
        inputs={
            "prompt": [prompt],
            "negative_prompt": [negative_prompt] if negative_prompt else None,
            "num_images_per_prompt": num_outputs,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "image": [image],
        },
    )


def instruct_pix2pix(
    *,
    prompt: str,
    num_outputs: int,
    images: typing.List[str],
    num_inference_steps: int,
    negative_prompt: str = None,
    guidance_scale: float,
    image_guidance_scale: float,
    seed: int = 42,
):
    return call_sd_multi(
        "diffusion.instruct_pix2pix",
        pipeline={
            "model_id": "timbrooks/instruct-pix2pix",
            # "scheduler": "UniPCMultistepScheduler",
            "disable_safety_checker": True,
            "seed": seed,
        },
        inputs={
            "prompt": [prompt] * len(images),
            "negative_prompt": (
                [negative_prompt] * len(images) if negative_prompt else None
            ),
            "num_images_per_prompt": num_outputs,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "image": images,
            "image_guidance_scale": image_guidance_scale,
        },
    )


def text2img(
    *,
    model: Text2ImgModels,
    prompt: str,
    num_outputs: int,
    num_inference_steps: int,
    width: int,
    height: int,
    seed: int = 42,
    guidance_scale: float = None,
    negative_prompt: str = None,
    scheduler: str = None,
    dall_e_3_quality: str | None = None,
    dall_e_3_style: str | None = None,
    gpt_image_1_quality: typing.Literal["low", "medium", "high"] | None = None,
    loras: list[LoraWeight] | None = None,
):
    if model not in {
        Text2ImgModels.dall_e_3,
        Text2ImgModels.flux_1_dev,
        Text2ImgModels.gpt_image_1,
        Text2ImgModels.nano_banana,
        Text2ImgModels.nano_banana_pro,
    }:
        _resolution_check(width, height, max_size=(1024, 1024))

    if model in Text2ImgModels._deprecated():
        raise UserError(f"Model {model.value} is deprecated")

    match model:
        case Text2ImgModels.flux_1_dev:
            payload = dict(
                prompt=prompt,
                image_size=dict(width=width, height=height),
                num_inference_steps=min(num_inference_steps, 50),
                seed=seed,
                guidance_scale=guidance_scale,
                num_images=num_outputs,
                enable_safety_checker=False,
            )
            if loras:
                payload["loras"] = [lora.model_dump() for lora in loras]
            output_images = yield from generate_fal_images(
                model_id=text2img_model_ids[model],
                payload=payload,
            )
            return output_images
        case Text2ImgModels.gpt_image_1 | Text2ImgModels.gpt_image_1_5:
            from openai import OpenAI

            client = OpenAI()
            width, height = _get_gpt_image_1_img_size(width, height)
            with capture_openai_content_policy_violation():
                response = client.images.generate(
                    model=text2img_model_ids[model],
                    prompt=prompt,
                    size=f"{width}x{height}",
                    quality=gpt_image_1_quality,
                )

            # Record usage costs using the API response usage data
            record_openai_image_generation_usage(
                model=text2img_model_ids[model],
                usage=response.usage,
            )

            out_imgs = [b64_img_decode(part.b64_json) for part in response.data]
        case Text2ImgModels.dall_e_3:
            from openai import OpenAI

            client = OpenAI()
            width, height = _get_dall_e_3_img_size(width, height)
            with capture_openai_content_policy_violation():
                response = client.images.generate(
                    model=text2img_model_ids[model],
                    n=1,  # num_outputs, not supported yet
                    prompt=prompt,
                    response_format="b64_json",
                    quality=dall_e_3_quality,
                    style=dall_e_3_style,
                    size=f"{width}x{height}",
                )
            out_imgs = [b64_img_decode(part.b64_json) for part in response.data]
        case Text2ImgModels.dall_e:
            from openai import OpenAI

            edge = _get_dall_e_img_size(width, height)
            client = OpenAI()
            with capture_openai_content_policy_violation():
                response = client.images.generate(
                    model=text2img_model_ids[model],
                    n=num_outputs,
                    prompt=prompt,
                    size=f"{edge}x{edge}",
                    response_format="b64_json",
                )
            out_imgs = [b64_img_decode(part.b64_json) for part in response.data]
        case Text2ImgModels.nano_banana | Text2ImgModels.nano_banana_pro:
            from usage_costs.cost_utils import record_cost_auto
            from usage_costs.models import ModelSku

            payload = dict(
                prompt=prompt, output_format="png", num_images=num_outputs
            ) | resolve_nano_banana_resolution(width, height)

            output_images = yield from generate_fal_images(
                model_id=text2img_model_ids[model],
                payload=payload,
            )

            if payload.get("resolution") == "4K":
                num_outputs *= 2  # 2x price for 4K
            record_cost_auto(
                model=text2img_model_ids[model],
                sku=ModelSku.output_image_tokens,
                quantity=num_outputs,
            )

            return output_images
        case _:
            prompt = add_prompt_prefix(prompt, model.name)
            return call_sd_multi(
                "diffusion.text2img",
                pipeline={
                    "model_id": text2img_model_ids[model],
                    "scheduler": Schedulers[scheduler].label if scheduler else None,
                    "disable_safety_checker": True,
                    "seed": seed,
                },
                inputs={
                    "prompt": [prompt],
                    "negative_prompt": [negative_prompt] if negative_prompt else None,
                    "num_images_per_prompt": num_outputs,
                    "num_inference_steps": num_inference_steps,
                    "guidance_scale": guidance_scale,
                    "width": width,
                    "height": height,
                },
            )

    return [
        upload_file_from_bytes(f"gooey.ai - {prompt}.png", sd_img_bytes)
        for sd_img_bytes in out_imgs
    ]


def resolve_nano_banana_resolution(width: int, height: int) -> dict:
    from daras_ai_v2.img_model_settings_widgets import (
        RESOLUTIONS,
        NANO_BANANA_RESOLUTIONS,
    )

    if width < height:
        res = f"{height} x {width}"
        portrait = True
    else:
        res = f"{width} x {height}"
        portrait = False
    for pixels in NANO_BANANA_RESOLUTIONS:
        try:
            aspect_ratio = RESOLUTIONS[pixels][res]
        except KeyError:
            continue
        if portrait:
            aspect_ratio = ":".join(aspect_ratio.split(":")[::-1])
        return {"resolution": pixels, "aspect_ratio": aspect_ratio}

    return {}


def generate_fal_images(
    model_id: str, payload: dict
) -> typing.Generator[str, None, list[str]]:
    result = yield from generate_on_fal(model_id, payload)
    return [r["url"] for r in result["images"]]


def _get_dall_e_img_size(width: int, height: int) -> typing.Literal[256, 512, 1024]:
    edge = max(width, height)
    if edge < 512:
        return 256
    elif 512 <= edge < 1024:
        return 512
    else:
        return 1024


def _get_dall_e_3_img_size(width: int, height: int) -> tuple[int, int]:
    if height == width:
        return 1024, 1024
    elif width < height:
        return 1024, 1792
    else:
        return 1792, 1024


def _get_gpt_image_1_img_size(width: int, height: int) -> tuple[int, int]:
    """
    Returns the appropriate size for GPT Image 1 based on input dimensions.
    Supported sizes: 1024x1024, 1536x1024, 1024x1536
    """
    if height == width:
        return 1024, 1024
    elif width > height:
        return 1536, 1024
    else:
        return 1024, 1536


def img2img(
    *,
    selected_model: str,
    prompt: str,
    num_outputs: int,
    init_images: str | list[str],
    init_image_bytes: bytes | list[bytes] = None,
    num_inference_steps: int,
    prompt_strength: float = None,
    negative_prompt: str = None,
    guidance_scale: float,
    seed: int = 42,
    gpt_image_1_quality: typing.Literal["low", "medium", "high"] | None = None,
) -> typing.Generator[str, None, list[str]]:
    from usage_costs.cost_utils import record_cost_auto
    from usage_costs.models import ModelSku

    if isinstance(init_images, str):
        init_images = [init_images]
    if isinstance(init_image_bytes, bytes):
        init_image_bytes = [init_image_bytes]

    prompt_strength = prompt_strength or 0.7
    assert 0 <= prompt_strength <= 0.9, "Prompt Strength must be in range [0, 0.9]"

    if not prompt and selected_model in (
        Img2ImgModels.flux_pro_kontext.name,
        Img2ImgModels.gpt_image_1.name,
        Img2ImgModels.gpt_image_1_5.name,
        Img2ImgModels.nano_banana.name,
        Img2ImgModels.nano_banana_pro.name,
    ):
        raise UserError("Text prompt is required for this model")

    match selected_model:
        case Img2ImgModels.flux_pro_kontext.name:
            # Flux Pro Kontext requires guidance_scale >= 1.0
            if guidance_scale < 1.0:
                guidance_scale = 1.0
            payload = dict(
                prompt=prompt,
                image_url=init_images[0],
                num_inference_steps=min(num_inference_steps, 50),
                seed=seed,
                guidance_scale=guidance_scale,
                num_images=num_outputs,
                enable_safety_checker=False,
            )
            output_images = yield from generate_fal_images(
                model_id=img2img_model_ids[Img2ImgModels[selected_model]],
                payload=payload,
            )

            record_cost_auto(
                model=img2img_model_ids[Img2ImgModels[selected_model]],
                sku=ModelSku.output_image_tokens,
                quantity=num_outputs,
            )

            return output_images
        case Img2ImgModels.gpt_image_1.name | Img2ImgModels.gpt_image_1_5.name:
            from openai import NOT_GIVEN, OpenAI

            payload_input_images = []
            for idx, image_bytes in enumerate(init_image_bytes):
                init_height, init_width, _ = bytes_to_cv2_img(image_bytes).shape
                _resolution_check(init_width, init_height)

                if selected_model == Img2ImgModels.dall_e.name:
                    edge = _get_dall_e_img_size(init_width, init_height)
                    width, height = edge, edge
                    response_format = "b64_json"
                else:
                    width, height = _get_gpt_image_1_img_size(init_width, init_height)
                    response_format = NOT_GIVEN

                image = resize_img_pad(image_bytes, (width, height))
                image = rgb_img_to_rgba(image)
                payload_input_images.append((f"image_{idx}.png", image))

            client = OpenAI()
            with capture_openai_content_policy_violation():
                response = client.images.edit(
                    model=img2img_model_ids[Img2ImgModels[selected_model]],
                    prompt=prompt,
                    image=payload_input_images,
                    n=num_outputs,
                    size=f"{width}x{height}",
                    response_format=response_format,
                    quality=gpt_image_1_quality,
                )

            # Record usage costs if usage data is available
            record_openai_image_generation_usage(
                model=img2img_model_ids[Img2ImgModels[selected_model]],
                usage=response.usage,
            )

            out_imgs = [
                resize_img_fit(b64_img_decode(part.b64_json), (width, height))
                for part in response.data
            ]
        case Img2ImgModels.nano_banana.name | Img2ImgModels.nano_banana_pro.name:
            payload = dict(
                prompt=prompt,
                image_urls=init_images,
                num_images=num_outputs,
                output_format="png",
            )

            output_images = yield from generate_fal_images(
                model_id=img2img_model_ids[Img2ImgModels[selected_model]],
                payload=payload,
            )

            record_cost_auto(
                model=img2img_model_ids[Img2ImgModels[selected_model]],
                sku=ModelSku.output_image_tokens,
                quantity=num_outputs,
            )

            return output_images
        case _:
            prompt = add_prompt_prefix(prompt, selected_model)
            return call_sd_multi(
                "diffusion.img2img",
                pipeline={
                    "model_id": img2img_model_ids[Img2ImgModels[selected_model]],
                    # "scheduler": "UniPCMultistepScheduler",
                    "disable_safety_checker": True,
                    "seed": seed,
                },
                inputs={
                    "prompt": [prompt],
                    "negative_prompt": [negative_prompt] if negative_prompt else None,
                    "num_images_per_prompt": num_outputs,
                    "num_inference_steps": num_inference_steps,
                    "guidance_scale": guidance_scale,
                    "image": init_images,
                    "strength": prompt_strength,
                },
            )
    return [
        upload_file_from_bytes(f"gooey.ai - {prompt}.png", sd_img_bytes)
        for sd_img_bytes in out_imgs
    ]


def controlnet(
    *,
    selected_model: str,
    selected_controlnet_model: str | list[str],
    scheduler: str = None,
    prompt: str,
    num_outputs: int = 1,
    init_images: list[str],
    num_inference_steps: int = 50,
    negative_prompt: str = None,
    guidance_scale: float = 7.5,
    seed: int = 42,
    controlnet_conditioning_scale: typing.List[float] | float = 1.0,
):
    if isinstance(selected_controlnet_model, str):
        selected_controlnet_model = [selected_controlnet_model]
    prompt = add_prompt_prefix(prompt, selected_model)
    return call_sd_multi(
        "diffusion.controlnet",
        pipeline={
            "model_id": text2img_model_ids[Text2ImgModels[selected_model]],
            "seed": seed,
            "scheduler": (
                Schedulers[scheduler].label if scheduler else "UniPCMultistepScheduler"
            ),
            "disable_safety_checker": True,
            "controlnet_model_id": [
                controlnet_model_ids[ControlNetModels[model]]
                for model in selected_controlnet_model
            ],
        },
        inputs={
            "prompt": [prompt],
            "negative_prompt": [negative_prompt] if negative_prompt else None,
            "num_images_per_prompt": num_outputs,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "image": init_images,
            "controlnet_conditioning_scale": controlnet_conditioning_scale,
            # "strength": prompt_strength,
        },
    )


def add_prompt_prefix(prompt: str, selected_model: str) -> str:
    match selected_model:
        case Text2ImgModels.openjourney.name:
            prompt = "mdjrny-v4 style " + prompt
        case Text2ImgModels.analog_diffusion.name:
            prompt = "analog style " + prompt
        case Text2ImgModels.protogen_5_3.name:
            prompt = "modelshoot style " + prompt
        case Text2ImgModels.dreamlike_2.name:
            prompt = "photo, " + prompt
    return prompt


def inpainting(
    *,
    selected_model: str,
    prompt: str,
    num_outputs: int,
    edit_image: str,
    edit_image_bytes: bytes = None,
    mask: str,
    mask_bytes: bytes = None,
    num_inference_steps: int,
    width: int,
    height: int,
    negative_prompt: str = None,
    guidance_scale: float,
    seed: int = 42,
) -> list[str]:
    _resolution_check(width, height)

    match selected_model:
        case InpaintingModels.dall_e.name:
            from openai import OpenAI

            edge = _get_dall_e_img_size(width, height)
            edit_image_bytes = resize_img_pad(edit_image_bytes, (edge, edge))
            mask_bytes = resize_img_pad(mask_bytes, (edge, edge))
            image = rgb_img_to_rgba(edit_image_bytes, mask_bytes)

            client = OpenAI()
            with capture_openai_content_policy_violation():
                response = client.images.edit(
                    prompt=prompt,
                    image=("image.png", image),
                    n=num_outputs,
                    size=f"{edge}x{edge}",
                    response_format="b64_json",
                )
            out_imgs = [b64_img_decode(part.b64_json) for part in response.data]

        case InpaintingModels.sd_2.name | InpaintingModels.runway_ml.name:
            out_imgs_urls = call_sd_multi(
                "diffusion.inpaint",
                pipeline={
                    "model_id": inpaint_model_ids[InpaintingModels[selected_model]],
                    "seed": seed,
                    # "scheduler": Schedulers[scheduler].label
                    # if scheduler
                    # else "UniPCMultistepScheduler",
                    "disable_safety_checker": True,
                },
                inputs={
                    "prompt": [prompt],
                    "negative_prompt": [negative_prompt] if negative_prompt else None,
                    "num_images_per_prompt": num_outputs,
                    "num_inference_steps": num_inference_steps,
                    "guidance_scale": guidance_scale,
                    "image": [edit_image],
                    "mask_image": [mask],
                },
            )
            out_imgs = []
            for url in out_imgs_urls:
                r = requests.get(url)
                raise_for_status(r)
                out_imgs.append(r.content)

        case _:
            raise UserError(f"Invalid inpainting model {selected_model}")

    out_imgs = _recomposite_inpainting_outputs(out_imgs, edit_image_bytes, mask_bytes)

    return [
        upload_file_from_bytes(f"gooey.ai - {prompt}.png", sd_img_bytes)
        for sd_img_bytes in out_imgs
    ]


def _recomposite_inpainting_outputs(
    out_imgs: list[bytes],
    orig_bytes: bytes,
    mask_bytes: bytes,
    cutdown_factor: float = 0.95,
) -> list[bytes]:
    """
    Pastes the original masked image back onto the output image for perfect results
    """

    ret = []

    for out_bytes in out_imgs:
        out_im = Image.open(io.BytesIO(out_bytes))
        orig_im = Image.open(io.BytesIO(orig_bytes))
        mask_im = Image.open(io.BytesIO(mask_bytes))

        cutdown_mask_size = (
            int(orig_im.size[0] * cutdown_factor),
            int(orig_im.size[1] * cutdown_factor),
        )
        mask_im = mask_im.convert("L").resize(cutdown_mask_size)

        result = Image.new("L", orig_im.size, (0,))
        paste_pos = (
            (orig_im.size[0] - mask_im.size[0]) // 2,
            (orig_im.size[1] - mask_im.size[1]) // 2,
        )
        result.paste(mask_im, paste_pos)
        result = Image.composite(orig_im, out_im, result)

        img_byte_arr = io.BytesIO()
        result.save(img_byte_arr, format="PNG")
        out_bytes = img_byte_arr.getvalue()

        ret.append(out_bytes)

    return ret


def _resolution_check(width, height, max_size=SD_IMG_MAX_SIZE):
    if get_downscale_factor(im_size=(width, height), max_size=max_size):
        raise ValueError(
            f"Maximum size is {max_size[0]}x{max_size[1]} pixels, because of memory limits. "
            f"Please select a lower width or height."
        )


def record_openai_image_generation_usage(
    model: str,
    usage: openai.types.images_response.Usage | None = None,
):
    """
    Record usage costs for OpenAI image generation models.

    Args:
        model: The model identifier (e.g., "gpt-image-1")
        usage: Usage object from OpenAI API response with token information
    """
    from usage_costs.cost_utils import record_cost_auto
    from usage_costs.models import ModelSku

    if not usage:
        return

    # Record text input usage (for text prompts)
    if text_input_tokens := usage.input_tokens_details.text_tokens:
        record_cost_auto(
            model=model,
            sku=ModelSku.llm_prompt,
            quantity=text_input_tokens,
        )

    # Record image input usage (for image inputs in img2img, editing)
    if input_image_tokens := usage.input_tokens_details.image_tokens:
        record_cost_auto(
            model=model,
            sku=ModelSku.input_image_tokens,
            quantity=input_image_tokens,
        )

    # Record output usage (for generated images/content)
    if output_image_tokens := usage.output_tokens:
        record_cost_auto(
            model=model,
            sku=ModelSku.output_image_tokens,
            quantity=output_image_tokens,
        )


def validate_multi_image_models(selected_model: Img2ImgModels, init_images: list[str]):
    if (
        len(init_images) > 1
        and selected_model not in Img2ImgModels._multi_image_models()
    ):
        supported_models = "\n".join(
            f"  - {model.value}" for model in Img2ImgModels._multi_image_models()
        )
        raise UserError(
            f"**{selected_model.value}** does not support multiple images. Please select one of the following models that supports multiple images:\n{supported_models}\n\nOr upload a single image."
        )

    if len(init_images) > 20:
        raise UserError("Maximum number of images is 20. Please upload fewer images.")
