import io
from enum import Enum

import openai
from PIL import Image

from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2 import settings
from daras_ai_v2.extract_face import rgb_img_to_rgba
from daras_ai_v2.gpu_server import call_gpu_server_b64, GpuEndpoints, b64_img_decode


class InpaintingModels(Enum):
    sd_2 = "Stable Diffusion 2 (stability.ai)"
    runway_ml = "Stable Diffusion v1.5 (RunwayML)"
    jack_qiao = "Stable Diffusion v1.4 (Jack Qiao)"
    dall_e = "Dall-E (OpenAI)"


class Img2ImgModels(Enum):
    # sd_1_4 = "SD v1.4 (RunwayML)" # Host this too?
    sd_2 = "Stable Diffusion 2 (stability.ai)"
    sd_1_5 = "Stable Diffusion v1.5 (RunwayML)"
    jack_qiao = "Stable Diffusion v1.4 (Jack Qiao)"
    dall_e = "Dall-E (OpenAI)"


class Text2ImgModels(Enum):
    # sd_1_4 = "SD v1.4 (RunwayML)" # Host this too?
    sd_2 = "Stable Diffusion 2 (stability.ai)"
    sd_1_5 = "Stable Diffusion v1.5 (RunwayML)"
    jack_qiao = "Stable Diffusion v1.4 (Jack Qiao)"
    # openjourney = "Open Journey (PromptHero)"
    dall_e = "Dall-E (OpenAI)"


def text2img(
    *,
    selected_model: str,
    prompt: str,
    num_outputs: int,
    num_inference_steps: int,
    width: int,
    height: int,
    guidance_scale: float = None,
    seed: float = None,
):
    _resolution_check(width, height)

    match selected_model:
        case Text2ImgModels.sd_2.name:
            out_imgs = call_gpu_server_b64(
                endpoint=GpuEndpoints.sd_2,
                input_data={
                    "prompt": prompt,
                    "width": width,
                    "height": height,
                    "num_outputs": num_outputs,
                    "num_inference_steps": num_inference_steps,
                    "guidance_scale": guidance_scale,
                    "seed": seed,
                    # "sampler": "ddim",
                },
            )
        case Text2ImgModels.jack_qiao.name:
            out_imgs = call_gpu_server_b64(
                endpoint=GpuEndpoints.glid_3_xl_stable,
                input_data={
                    "prompt": prompt,
                    "num_inference_steps": num_inference_steps,
                    # "init_image": init_image,
                    # "edit_image": edit_image,
                    # "mask": mask,
                    "num_outputs": num_outputs,
                    # "negative_prompt": "string",
                    # "outpaint": "expand",
                    # "skip_timesteps": int(num_inference_steps * (1 - prompt_strength)),
                    "width": width,
                    "height": height,
                },
            )
        case Text2ImgModels.dall_e.name:
            openai.api_key = settings.OPENAI_API_KEY
            openai.api_base = "https://api.openai.com/v1"

            response = openai.Image.create(
                n=num_outputs,
                prompt=prompt,
                size=f"{width}x{height}",
                response_format="b64_json",
            )
            out_imgs = [b64_img_decode(part["b64_json"]) for part in response["data"]]
        case Text2ImgModels.sd_1_5.name:
            out_imgs = call_gpu_server_b64(
                endpoint=GpuEndpoints.sd_1_5,
                input_data={
                    "prompt": prompt,
                    "width": width,
                    "height": height,
                    # "init_image": init_image,
                    # "mask": "string",
                    # "prompt_strength": prompt_strength,
                    "num_outputs": num_outputs,
                    "num_inference_steps": num_inference_steps,
                    "guidance_scale": guidance_scale,
                    # "scheduler": "K-LMS",
                    "seed": seed,
                },
            )
        case _:
            out_imgs = []
    return [
        upload_file_from_bytes(f"gooey.ai - {prompt}.png", sd_img_bytes)
        for sd_img_bytes in out_imgs
    ]


def img2img(
    *,
    selected_model: str,
    prompt: str,
    num_outputs: int,
    init_image: str,
    init_image_bytes: bytes = None,
    num_inference_steps: int,
    width: int,
    height: int,
    prompt_strength: float,
):
    _resolution_check(width, height)

    match selected_model:
        case Img2ImgModels.sd_2.name:
            out_imgs = call_gpu_server_b64(
                endpoint=GpuEndpoints.sd_2,
                input_data={
                    "prompt": prompt,
                    "width": width,
                    "height": height,
                    "num_outputs": num_outputs,
                    "num_inference_steps": num_inference_steps,
                    "init_image": init_image,
                    "strength": prompt_strength,
                    # "sampler": "ddim",
                    "guidance_scale": 10,
                    # "seed": seed,
                },
            )
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
                    # "negative_prompt": "string",
                    # "outpaint": "expand",
                    "skip_timesteps": int(num_inference_steps * (1 - prompt_strength)),
                    "width": width,
                    "height": height,
                },
            )
        case Img2ImgModels.dall_e.name:
            openai.api_key = settings.OPENAI_API_KEY
            openai.api_base = "https://api.openai.com/v1"

            response = openai.Image.create_variation(
                image=init_image_bytes,
                n=num_outputs,
                size=f"{width}x{height}",
                response_format="b64_json",
            )
            out_imgs = [b64_img_decode(part["b64_json"]) for part in response["data"]]
        case Img2ImgModels.sd_1_5.name:
            out_imgs = call_gpu_server_b64(
                endpoint=GpuEndpoints.sd_1_5,
                input_data={
                    "prompt": prompt,
                    "width": width,
                    "height": height,
                    "init_image": init_image,
                    # "mask": "string",
                    "prompt_strength": prompt_strength,
                    "num_outputs": num_outputs,
                    "num_inference_steps": num_inference_steps,
                    # "guidance_scale": 7.5,
                    # "scheduler": "K-LMS",
                    # "seed": 0,
                },
            )
        case _:
            out_imgs = []
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
) -> list[str]:
    _resolution_check(width, height)

    match selected_model:
        case InpaintingModels.sd_2.name:
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
                    "guidance_scale": 10,
                    # "seed": seed,
                    # "sampler": "ddim",
                },
            )
        case InpaintingModels.runway_ml.name:
            out_imgs = call_gpu_server_b64(
                endpoint=GpuEndpoints.runway_ml_inpainting,
                input_data={
                    "prompt": prompt,
                    "image": edit_image,
                    "mask": mask,
                    "invert_mask": True,
                    "num_outputs": num_outputs,
                    "num_inference_steps": num_inference_steps,
                    # "guidance_scale": "...",
                    # "seed": "...",
                },
            )
        case InpaintingModels.dall_e.name:
            openai.api_key = settings.OPENAI_API_KEY
            openai.api_base = "https://api.openai.com/v1"

            response = openai.Image.create_edit(
                prompt=prompt,
                image=rgb_img_to_rgba(edit_image_bytes, mask_bytes),
                mask=None,
                n=num_outputs,
                size=f"{width}x{height}",
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
                    # "negative_prompt": "string",
                    # "outpaint": "expand",
                    # "skip_timesteps": 0,
                    "width": width,
                    "height": height,
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
    if width * height > 768 * 768:
        raise ValueError(
            "Maximum size is 768x768 pixels, because of memory limits. Please select a lower width or height."
        )
