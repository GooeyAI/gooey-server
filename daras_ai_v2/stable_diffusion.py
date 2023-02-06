import io
import typing
from enum import Enum

import openai
import replicate
import requests
from PIL import Image

from daras_ai.image_input import (
    upload_file_from_bytes,
    bytes_to_cv2_img,
    resize_img_pad,
    resize_img_fit,
)
from daras_ai_v2 import settings
from daras_ai_v2.extract_face import rgb_img_to_rgba
from daras_ai_v2.gpu_server import (
    call_gpu_server_b64,
    GpuEndpoints,
    b64_img_decode,
    call_sd_multi,
)

IMG_MAX_SIZE = (768, 768)


class InpaintingModels(Enum):
    sd_2 = "Stable Diffusion v2.1 (stability.ai)"
    runway_ml = "Stable Diffusion v1.5 (RunwayML)"
    jack_qiao = "Stable Diffusion v1.4 (Jack Qiao)"
    dall_e = "Dall-E (OpenAI)"


class Img2ImgModels(Enum):
    # sd_1_4 = "SD v1.4 (RunwayML)" # Host this too?
    instruct_pix2pix = "✨ InstructPix2Pix (Tim Brooks)"
    sd_2 = "Stable Diffusion v2.1 (stability.ai)"
    sd_1_5 = "Stable Diffusion v1.5 (RunwayML)"
    jack_qiao = "Stable Diffusion v1.4 (Jack Qiao)"
    dall_e = "Dall-E (OpenAI)"
    openjourney = "Open Journey (PromptHero)"
    openjourney_2 = "Open Journey v2 beta (PromptHero)"
    analog_diffusion = "Analog Diffusion (wavymulder)"
    protogen_5_3 = "Protogen v5.3 (darkstorm2150)"
    dreamlike_2 = "Dreamlike Photoreal 2.0 (dreamlike.art)"


class Text2ImgModels(Enum):
    # sd_1_4 = "SD v1.4 (RunwayML)" # Host this too?
    sd_2 = "Stable Diffusion v2.1 (stability.ai)"
    sd_1_5 = "Stable Diffusion v1.5 (RunwayML)"
    jack_qiao = "Stable Diffusion v1.4 (Jack Qiao)"
    openjourney = "Open Journey (PromptHero)"
    openjourney_2 = "Open Journey v2 beta (PromptHero)"
    analog_diffusion = "Analog Diffusion (wavymulder)"
    protogen_5_3 = "Protogen v5.3 (darkstorm2150)"
    dreamlike_2 = "Dreamlike Photoreal 2.0 (dreamlike.art)"
    dall_e = "Dall-E (OpenAI)"


def sd_upscale(
    *,
    prompt: str,
    num_outputs: int,
    image: str,
    num_inference_steps: int,
    negative_prompt: str = None,
    guidance_scale: float = None,
    seed: int = 42,
):
    return call_sd_multi(
        "upscale",
        pipeline={
            "model_id": "stabilityai/stable-diffusion-x4-upscaler",
            # "scheduler": None,
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
    guidance_scale: float = None,
    image_guidance_scale: float,
    seed: int = 42,
):
    return call_sd_multi(
        "instruct_pix2pix",
        pipeline={
            "model_id": "timbrooks/instruct-pix2pix",
            # "scheduler": None,
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
):
    _resolution_check(width, height)

    match selected_model:
        case Text2ImgModels.jack_qiao.name:
            out_imgs = call_gpu_server_b64(
                endpoint=GpuEndpoints.glid_3_xl_stable,
                input_data={
                    "prompt": prompt,
                    "num_inference_steps": num_inference_steps,
                    "num_outputs": num_outputs,
                    "negative_prompt": negative_prompt or "",
                    "width": width,
                    "height": height,
                },
            )
        case Text2ImgModels.dall_e.name:
            openai.api_key = settings.OPENAI_API_KEY
            openai.api_base = "https://api.openai.com/v1"

            edge = _get_dalle_img_size(width, height)
            response = openai.Image.create(
                n=num_outputs,
                prompt=prompt,
                size=f"{edge}x{edge}",
                response_format="b64_json",
            )
            out_imgs = [b64_img_decode(part["b64_json"]) for part in response["data"]]
        case _:
            match selected_model:
                case Text2ImgModels.sd_1_5.name:
                    hf_model_id = "runwayml/stable-diffusion-v1-5"
                case Text2ImgModels.sd_2.name:
                    hf_model_id = "stabilityai/stable-diffusion-2-1"
                case Text2ImgModels.openjourney.name:
                    prompt = "mdjrny-v4 style " + prompt
                    hf_model_id = "prompthero/openjourney"
                case Text2ImgModels.openjourney_2.name:
                    hf_model_id = "prompthero/openjourney-v2"
                case Text2ImgModels.analog_diffusion.name:
                    prompt = "analog style " + prompt
                    hf_model_id = "wavymulder/Analog-Diffusion"
                case Text2ImgModels.protogen_5_3.name:
                    prompt = "modelshoot style " + prompt
                    hf_model_id = "darkstorm2150/Protogen_v5.3_Official_Release"
                case Text2ImgModels.dreamlike_2.name:
                    prompt = "photo, " + prompt
                    hf_model_id = "dreamlike-art/dreamlike-photoreal-2.0"
                case _:
                    return []
            return call_sd_multi(
                "text2img",
                pipeline={
                    "model_id": hf_model_id,
                    # "scheduler": None,
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
    guidance_scale: float = None,
    sd_2_upscaling: bool = False,
    seed: int = 42,
):
    prompt_strength = prompt_strength or 0.7
    assert 0 <= prompt_strength <= 0.9, "Prompt Strength must be in range [0, 0.9]"

    height, width, _ = bytes_to_cv2_img(init_image_bytes).shape
    _resolution_check(width, height)

    match selected_model:
        case Img2ImgModels.jack_qiao.name:
            out_imgs = call_gpu_server_b64(
                endpoint=GpuEndpoints.glid_3_xl_stable,
                input_data={
                    "prompt": prompt,
                    "num_inference_steps": num_inference_steps,
                    "init_image": init_image,
                    # "edit_image": edit_image,
                    # "mask": mask,
                    "num_outputs": num_outputs,
                    "negative_prompt": negative_prompt or "",
                    # "outpaint": "expand",
                    "skip_timesteps": int(num_inference_steps * (1 - prompt_strength)),
                    "width": width,
                    "height": height,
                    "seed": seed,
                },
            )
        case Img2ImgModels.dall_e.name:
            openai.api_key = settings.OPENAI_API_KEY
            openai.api_base = "https://api.openai.com/v1"

            edge = _get_dalle_img_size(width, height)
            image = resize_img_pad(init_image_bytes, (edge, edge))

            response = openai.Image.create_variation(
                image=image,
                n=num_outputs,
                size=f"{edge}x{edge}",
                response_format="b64_json",
            )

            out_imgs = [
                resize_img_fit(b64_img_decode(part["b64_json"]), (width, height))
                for part in response["data"]
            ]
        case _:
            match selected_model:
                case Img2ImgModels.sd_1_5.name:
                    hf_model_id = "runwayml/stable-diffusion-v1-5"
                case Img2ImgModels.sd_2.name:
                    hf_model_id = "stabilityai/stable-diffusion-2-1"
                case Img2ImgModels.openjourney.name:
                    prompt = "mdjrny-v4 style " + prompt
                    hf_model_id = "prompthero/openjourney"
                case Img2ImgModels.openjourney_2.name:
                    hf_model_id = "prompthero/openjourney-v2"
                case Img2ImgModels.analog_diffusion.name:
                    prompt = "analog style " + prompt
                    hf_model_id = "wavymulder/Analog-Diffusion"
                case Img2ImgModels.protogen_5_3.name:
                    prompt = "modelshoot style " + prompt
                    hf_model_id = "darkstorm2150/Protogen_v5.3_Official_Release"
                case Img2ImgModels.dreamlike_2.name:
                    prompt = "photo, " + prompt
                    hf_model_id = "dreamlike-art/dreamlike-photoreal-2.0"
                case _:
                    return []
            return call_sd_multi(
                "img2img",
                pipeline={
                    "model_id": hf_model_id,
                    # "scheduler": None,
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
    guidance_scale: float = None,
    seed: int = 42,
) -> list[str]:
    _resolution_check(width, height)

    match selected_model:
        case InpaintingModels.sd_2.name:
            if num_inference_steps == 110:
                num_inference_steps = 100
            out_imgs = call_gpu_server_b64(
                endpoint=GpuEndpoints.sd_2,
                input_data={
                    "prompt": prompt,
                    "width": width,
                    "height": height,
                    "num_outputs": num_outputs,
                    "num_inference_steps": num_inference_steps,
                    "edit_image": edit_image,
                    "mask_image": mask,
                    "guidance_scale": guidance_scale,
                    "negative_prompt": negative_prompt or "",
                    "seed": seed,
                },
            )
        case InpaintingModels.runway_ml.name:
            model = replicate.models.get("andreasjansson/stable-diffusion-inpainting")
            version = model.versions.get(
                "8eb2da8345bee796efcd925573f077e36ed5fb4ea3ba240ef70c23cf33f0d848"
            )
            out_imgs = [
                requests.get(img).content
                for img in version.predict(
                    prompt=prompt,
                    image=edit_image,
                    mask=mask,
                    invert_mask=True,
                    num_outputs=num_outputs,
                    num_inference_steps=num_inference_steps,
                    guidance_scale=guidance_scale,
                    seed=seed,
                )
            ]
        case InpaintingModels.dall_e.name:
            openai.api_key = settings.OPENAI_API_KEY
            openai.api_base = "https://api.openai.com/v1"

            edge = _get_dalle_img_size(width, height)
            edit_image_bytes = resize_img_pad(edit_image_bytes, (edge, edge))
            mask_bytes = resize_img_pad(mask_bytes, (edge, edge))
            image = rgb_img_to_rgba(edit_image_bytes, mask_bytes)

            response = openai.Image.create_edit(
                prompt=prompt,
                image=image,
                mask=None,
                n=num_outputs,
                size=f"{edge}x{edge}",
                response_format="b64_json",
            )
            out_imgs = [b64_img_decode(part["b64_json"]) for part in response["data"]]
        case _:
            out_imgs = call_gpu_server_b64(
                endpoint=GpuEndpoints.glid_3_xl_stable,
                input_data={
                    "prompt": prompt,
                    "num_inference_steps": num_inference_steps,
                    # "init_image": "string",
                    "edit_image": edit_image,
                    "mask": mask,
                    "num_outputs": num_outputs,
                    "negative_prompt": negative_prompt or "",
                    # "negative_prompt": "string",
                    # "outpaint": "expand",
                    # "skip_timesteps": 0,
                    "width": width,
                    "height": height,
                    "seed": seed,
                },
            )

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


def _resolution_check(width, height):
    if width * height > IMG_MAX_SIZE[0] * IMG_MAX_SIZE[1]:
        raise ValueError(
            f"Maximum size is {IMG_MAX_SIZE[0]}x{IMG_MAX_SIZE[1]} pixels, because of memory limits. "
            f"Please select a lower width or height."
        )
