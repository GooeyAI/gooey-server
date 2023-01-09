import io
from enum import Enum

import openai
import replicate
import requests
from PIL import Image

from daras_ai.image_input import upload_file_from_bytes, bytes_to_cv2_img
from daras_ai_v2 import settings
from daras_ai_v2.extract_face import rgb_img_to_rgba
from daras_ai_v2.gpu_server import call_gpu_server_b64, GpuEndpoints, b64_img_decode

SD_MAX_SIZE = (768, 768)


class InpaintingModels(Enum):
    sd_2 = "Stable Diffusion 2 (stability.ai)"
    runway_ml = "Stable Diffusion v1.5 (RunwayML)"
    jack_qiao = "Stable Diffusion v1.4 (Jack Qiao)"
    dall_e = "Dall-E (OpenAI)"


class Img2ImgModels(Enum):
    # sd_1_4 = "SD v1.4 (RunwayML)" # Host this too?
    sd_2 = "Stable Diffusion v2.1 (stability.ai)"
    sd_1_5 = "Stable Diffusion v1.5 (RunwayML)"
    jack_qiao = "Stable Diffusion v1.4 (Jack Qiao)"
    dall_e = "Dall-E (OpenAI)"
    openjourney = "Open Journey (PromptHero)"
    openjourney_2 = "Open Journey v2 beta (PromptHero)"
    analog_diffusion = "Analog Diffusion (wavymulder)"
    protogen_5_3 = "Protogen v5.3 (darkstorm2150)"


class Text2ImgModels(Enum):
    # sd_1_4 = "SD v1.4 (RunwayML)" # Host this too?
    sd_2 = "Stable Diffusion v2.1 (stability.ai)"
    sd_1_5 = "Stable Diffusion v1.5 (RunwayML)"
    jack_qiao = "Stable Diffusion v1.4 (Jack Qiao)"
    openjourney = "Open Journey (PromptHero)"
    openjourney_2 = "Open Journey v2 beta (PromptHero)"
    analog_diffusion = "Analog Diffusion (wavymulder)"
    protogen_5_3 = "Protogen v5.3 (darkstorm2150)"
    dall_e = "Dall-E (OpenAI)"


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
    sd_2_upscaling: bool = False,
    negative_prompt: str = None,
):
    _resolution_check(width, height)

    match selected_model:
        case Text2ImgModels.sd_2.name:
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
                    "guidance_scale": guidance_scale,
                    "seed": seed,
                    "upscaling_inference_steps": 10 if sd_2_upscaling else 0,
                    "negative_prompt": negative_prompt or "",
                },
            )
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

            if 512 < width < 1024:
                width = 512
            if 512 < height < 1024:
                height = 512

            response = openai.Image.create(
                n=num_outputs,
                prompt=prompt,
                size=f"{width}x{height}",
                response_format="b64_json",
            )
            out_imgs = [b64_img_decode(part["b64_json"]) for part in response["data"]]
        case _:
            match selected_model:
                case Text2ImgModels.sd_1_5.name:
                    hf_model_id = "runwayml/stable-diffusion-v1-5"
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
                case _:
                    return []
            out_imgs = call_gpu_server_b64(
                endpoint=GpuEndpoints.sd_multi,
                input_data={
                    "hf_model_id": hf_model_id,
                    "prompt": prompt,
                    "width": width,
                    "height": height,
                    "num_outputs": num_outputs,
                    "num_inference_steps": num_inference_steps,
                    "guidance_scale": guidance_scale,
                    "seed": seed,
                    "negative_prompt": negative_prompt or "",
                },
            )
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
    prompt_strength: float,
    negative_prompt: str = None,
    guidance_scale: float = None,
    sd_2_upscaling: bool = False,
    seed: int = 42,
):
    assert 0 <= prompt_strength <= 0.9, "Prompt Strength must be in range [0, 0.9]"

    height, width, _ = bytes_to_cv2_img(init_image_bytes).shape
    _resolution_check(width, height)

    match selected_model:
        case Img2ImgModels.sd_2.name:
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
                    "init_image": init_image,
                    "strength": prompt_strength,
                    "guidance_scale": guidance_scale,
                    "negative_prompt": negative_prompt or "",
                    "upscaling_inference_steps": 10 if sd_2_upscaling else 0,
                    "seed": seed,
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

            if 512 < width < 1024:
                width = 512
            if 512 < height < 1024:
                height = 512

            response = openai.Image.create_variation(
                image=init_image_bytes,
                n=num_outputs,
                size=f"{width}x{height}",
                response_format="b64_json",
            )
            out_imgs = [b64_img_decode(part["b64_json"]) for part in response["data"]]
        case _:
            match selected_model:
                case Img2ImgModels.sd_1_5.name:
                    hf_model_id = "runwayml/stable-diffusion-v1-5"
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
                case _:
                    return []
            out_imgs = call_gpu_server_b64(
                endpoint=GpuEndpoints.sd_multi,
                input_data={
                    "hf_model_id": hf_model_id,
                    "prompt": prompt,
                    "width": width,
                    "height": height,
                    "num_outputs": num_outputs,
                    "num_inference_steps": num_inference_steps,
                    "guidance_scale": guidance_scale,
                    "seed": seed,
                    "negative_prompt": negative_prompt or "",
                    "init_image": init_image,
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
    if width * height > SD_MAX_SIZE[0] * SD_MAX_SIZE[1]:
        raise ValueError(
            f"Maximum size is {SD_MAX_SIZE[0]}x{SD_MAX_SIZE[1]} pixels, because of memory limits. "
            f"Please select a lower width or height."
        )
