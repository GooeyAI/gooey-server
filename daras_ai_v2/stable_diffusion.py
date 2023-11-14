import io
import typing
from enum import Enum

import requests
from PIL import Image
from django.db import models

from daras_ai.image_input import (
    upload_file_from_bytes,
    bytes_to_cv2_img,
    resize_img_pad,
    resize_img_fit,
    get_downscale_factor,
)
from daras_ai_v2.extract_face import rgb_img_to_rgba
from daras_ai_v2.gpu_server import (
    b64_img_decode,
    call_sd_multi,
)

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
    # sd_1_4 = "SD v1.4 (RunwayML)" # Host this too?
    sd_2 = "Stable Diffusion v2.1 (stability.ai)"
    sd_1_5 = "Stable Diffusion v1.5 (RunwayML)"
    dream_shaper = "DreamShaper (Lykon)"
    openjourney = "Open Journey (PromptHero)"
    openjourney_2 = "Open Journey v2 beta (PromptHero)"
    analog_diffusion = "Analog Diffusion (wavymulder)"
    protogen_5_3 = "Protogen v5.3 (darkstorm2150)"
    dreamlike_2 = "Dreamlike Photoreal 2.0 (dreamlike.art)"
    dall_e = "DALL·E 2 (OpenAI)"
    dall_e_3 = "DALL·E 3 (OpenAI)"

    jack_qiao = "Stable Diffusion v1.4 [Deprecated] (Jack Qiao)"
    deepfloyd_if = "DeepFloyd IF [Deprecated] (stability.ai)"
    rodent_diffusion_1_5 = "Rodent Diffusion 1.5 [Deprecated] (NerdyRodent)"

    @classmethod
    def _deprecated(cls):
        return {cls.jack_qiao, cls.deepfloyd_if, cls.rodent_diffusion_1_5}


text2img_model_ids = {
    Text2ImgModels.sd_1_5: "runwayml/stable-diffusion-v1-5",
    Text2ImgModels.sd_2: "stabilityai/stable-diffusion-2-1",
    Text2ImgModels.dream_shaper: "Lykon/DreamShaper",
    Text2ImgModels.analog_diffusion: "wavymulder/Analog-Diffusion",
    Text2ImgModels.openjourney: "prompthero/openjourney",
    Text2ImgModels.openjourney_2: "prompthero/openjourney-v2",
    Text2ImgModels.dreamlike_2: "dreamlike-art/dreamlike-photoreal-2.0",
    Text2ImgModels.protogen_5_3: "darkstorm2150/Protogen_v5.3_Official_Release",
    Text2ImgModels.dall_e: "dall-e-2",
    Text2ImgModels.dall_e_3: "dall-e-3",
}


class Img2ImgModels(Enum):
    # sd_1_4 = "SD v1.4 (RunwayML)" # Host this too?
    instruct_pix2pix = "✨ InstructPix2Pix (Tim Brooks)"
    sd_2 = "Stable Diffusion v2.1 (stability.ai)"
    sd_1_5 = "Stable Diffusion v1.5 (RunwayML)"
    dream_shaper = "DreamShaper (Lykon)"
    openjourney = "Open Journey (PromptHero)"
    openjourney_2 = "Open Journey v2 beta (PromptHero)"
    analog_diffusion = "Analog Diffusion (wavymulder)"
    protogen_5_3 = "Protogen v5.3 (darkstorm2150)"
    dreamlike_2 = "Dreamlike Photoreal 2.0 (dreamlike.art)"
    dall_e = "Dall-E (OpenAI)"

    jack_qiao = "Stable Diffusion v1.4 [Deprecated] (Jack Qiao)"
    rodent_diffusion_1_5 = "Rodent Diffusion 1.5 [Deprecated] (NerdyRodent)"

    @classmethod
    def _deprecated(cls):
        return {cls.jack_qiao, cls.rodent_diffusion_1_5}


img2img_model_ids = {
    Img2ImgModels.sd_2: "stabilityai/stable-diffusion-2-1",
    Img2ImgModels.sd_1_5: "runwayml/stable-diffusion-v1-5",
    Img2ImgModels.dream_shaper: "Lykon/DreamShaper",
    Img2ImgModels.openjourney: "prompthero/openjourney",
    Img2ImgModels.openjourney_2: "prompthero/openjourney-v2",
    Img2ImgModels.analog_diffusion: "wavymulder/Analog-Diffusion",
    Img2ImgModels.protogen_5_3: "darkstorm2150/Protogen_v5.3_Official_Release",
    Img2ImgModels.dreamlike_2: "dreamlike-art/dreamlike-photoreal-2.0",
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
    return call_sd_multi(
        "diffusion.upscale",
        pipeline={
            "model_id": "stabilityai/stable-diffusion-x4-upscaler",
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
            "negative_prompt": [negative_prompt] * len(images)
            if negative_prompt
            else None,
            "num_images_per_prompt": num_outputs,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "image": images,
            "image_guidance_scale": image_guidance_scale,
        },
    )


def text2img(
    *,
    selected_model: str,
    prompt: str,
    num_outputs: int,
    num_inference_steps: int,
    width: int,
    height: int,
    seed: int = 42,
    guidance_scale: float = None,
    negative_prompt: str = None,
    scheduler: str = None,
):
    if selected_model != Text2ImgModels.dall_e_3.name:
        _resolution_check(width, height, max_size=(1024, 1024))

    match selected_model:
        case Text2ImgModels.dall_e_3.name:
            from openai import OpenAI

            client = OpenAI()
            width, height = _get_dalle_3_img_size(width, height)
            response = client.images.generate(
                model=text2img_model_ids[Text2ImgModels[selected_model]],
                n=num_outputs,
                prompt=prompt,
                response_format="b64_json",
                size=f"{width}x{height}",
            )
            out_imgs = [b64_img_decode(part.b64_json) for part in response.data]
        case Text2ImgModels.dall_e.name:
            from openai import OpenAI

            edge = _get_dalle_img_size(width, height)
            client = OpenAI()
            response = client.images.generate(
                n=num_outputs,
                prompt=prompt,
                size=f"{edge}x{edge}",
                response_format="b64_json",
            )
            out_imgs = [b64_img_decode(part.b64_json) for part in response.data]
        case _:
            prompt = add_prompt_prefix(prompt, selected_model)
            return call_sd_multi(
                "diffusion.text2img",
                pipeline={
                    "model_id": text2img_model_ids[Text2ImgModels[selected_model]],
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


def _get_dalle_img_size(width: int, height: int) -> int:
    edge = max(width, height)
    if edge < 512:
        edge = 256
    elif 512 < edge < 1024:
        edge = 512
    elif edge > 1024:
        edge = 1024
    return edge


def _get_dalle_3_img_size(width: int, height: int) -> tuple[int, int]:
    if height == width:
        return 1024, 1024
    elif width < height:
        return 1024, 1792
    else:
        return 1792, 1024


def img2img(
    *,
    selected_model: str,
    prompt: str,
    num_outputs: int,
    init_image: str,
    init_image_bytes: bytes = None,
    num_inference_steps: int,
    prompt_strength: float = None,
    negative_prompt: str = None,
    guidance_scale: float,
    seed: int = 42,
):
    prompt_strength = prompt_strength or 0.7
    assert 0 <= prompt_strength <= 0.9, "Prompt Strength must be in range [0, 0.9]"

    height, width, _ = bytes_to_cv2_img(init_image_bytes).shape
    _resolution_check(width, height)

    match selected_model:
        case Img2ImgModels.dall_e.name:
            from openai import OpenAI

            edge = _get_dalle_img_size(width, height)
            image = resize_img_pad(init_image_bytes, (edge, edge))

            client = OpenAI()
            response = client.images.create_variation(
                image=image,
                n=num_outputs,
                size=f"{edge}x{edge}",
                response_format="b64_json",
            )

            out_imgs = [
                resize_img_fit(b64_img_decode(part.b64_json), (width, height))
                for part in response.data
            ]
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
                    "image": [init_image],
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
    init_image: str,
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
            "scheduler": Schedulers[scheduler].label
            if scheduler
            else "UniPCMultistepScheduler",
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
            "image": [init_image] * len(selected_controlnet_model),
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

            edge = _get_dalle_img_size(width, height)
            edit_image_bytes = resize_img_pad(edit_image_bytes, (edge, edge))
            mask_bytes = resize_img_pad(mask_bytes, (edge, edge))
            image = rgb_img_to_rgba(edit_image_bytes, mask_bytes)

            client = OpenAI()
            response = client.images.edit(
                prompt=prompt,
                image=image,
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
                r.raise_for_status()
                out_imgs.append(r.content)

        case _:
            raise ValueError(f"Invalid model {selected_model}")

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
