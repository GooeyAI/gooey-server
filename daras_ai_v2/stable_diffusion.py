import io
import typing

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
from daras_ai_v2.custom_enum import GooeyEnum
from daras_ai_v2.exceptions import (
    raise_for_status,
    UserError,
)
from daras_ai_v2.extract_face import rgb_img_to_rgba
from daras_ai_v2.gpu_server import (
    b64_img_decode,
    call_sd_multi,
)
from daras_ai_v2.safety_checker import capture_openai_content_policy_violation

SD_IMG_MAX_SIZE = (768, 768)


class InpaintingModel(typing.NamedTuple):
    model_id: str | None
    label: str


class InpaintingModels(InpaintingModel, GooeyEnum):
    sd_2 = InpaintingModel(
        label="Stable Diffusion v2.1 (stability.ai)",
        model_id="stabilityai/stable-diffusion-2-inpainting",
    )
    runway_ml = InpaintingModel(
        label="Stable Diffusion v1.5 (RunwayML)",
        model_id="runwayml/stable-diffusion-inpainting",
    )
    dall_e = InpaintingModel(label="Dall-E (OpenAI)", model_id="dall-e-2")

    jack_qiao = InpaintingModel(
        label="Stable Diffusion v1.4 [Deprecated] (Jack Qiao)", model_id=None
    )

    @classmethod
    def _deprecated(cls):
        return {cls.jack_qiao}


class Text2ImgModel(typing.NamedTuple):
    model_id: str | None
    label: str


class Text2ImgModels(Text2ImgModel, GooeyEnum):
    # sd_1_4 = "SD v1.4 (RunwayML)" # Host this too?
    dream_shaper = Text2ImgModel(
        label="DreamShaper (Lykon)", model_id="Lykon/DreamShaper"
    )
    dreamlike_2 = Text2ImgModel(
        label="Dreamlike Photoreal 2.0 (dreamlike.art)",
        model_id="dreamlike-art/dreamlike-photoreal-2.0",
    )
    sd_2 = Text2ImgModel(
        label="Stable Diffusion v2.1 (stability.ai)",
        model_id="stabilityai/stable-diffusion-2-1",
    )
    sd_1_5 = Text2ImgModel(
        label="Stable Diffusion v1.5 (RunwayML)",
        model_id="runwayml/stable-diffusion-v1-5",
    )

    dall_e = Text2ImgModel(label="DALL·E 2 (OpenAI)", model_id="dall-e-2")
    dall_e_3 = Text2ImgModel(label="DALL·E 3 (OpenAI)", model_id="dall-e-3")

    openjourney_2 = Text2ImgModel(
        label="Open Journey v2 beta (PromptHero)", model_id="prompthero/openjourney-v2"
    )
    openjourney = Text2ImgModel(
        label="Open Journey (PromptHero)", model_id="prompthero/openjourney"
    )
    analog_diffusion = Text2ImgModel(
        label="Analog Diffusion (wavymulder)", model_id="wavymulder/Analog-Diffusion"
    )
    protogen_5_3 = Text2ImgModel(
        label="Protogen v5.3 (darkstorm2150)",
        model_id="darkstorm2150/Protogen_v5.3_Official_Release",
    )

    jack_qiao = Text2ImgModel(
        label="Stable Diffusion v1.4 [Deprecated] (Jack Qiao)", model_id=None
    )
    rodent_diffusion_1_5 = Text2ImgModel(
        label="Rodent Diffusion 1.5 [Deprecated] (NerdyRodent)", model_id=None
    )
    deepfloyd_if = Text2ImgModel(
        label="DeepFloyd IF [Deprecated] (stability.ai)", model_id=None
    )

    @classmethod
    def _deprecated(cls):
        return {cls.jack_qiao, cls.deepfloyd_if, cls.rodent_diffusion_1_5}


class Img2ImgModel(typing.NamedTuple):
    model_id: str | None
    label: str


class Img2ImgModels(Img2ImgModel, GooeyEnum):
    dream_shaper = Img2ImgModel(
        label="DreamShaper (Lykon)", model_id="Lykon/DreamShaper"
    )
    dreamlike_2 = Img2ImgModel(
        label="Dreamlike Photoreal 2.0 (dreamlike.art)",
        model_id="dreamlike-art/dreamlike-photoreal-2.0",
    )
    sd_2 = Img2ImgModel(
        label="Stable Diffusion v2.1 (stability.ai)",
        model_id="stabilityai/stable-diffusion-2-1",
    )
    sd_1_5 = Img2ImgModel(
        label="Stable Diffusion v1.5 (RunwayML)",
        model_id="runwayml/stable-diffusion-v1-5",
    )

    dall_e = Img2ImgModel(label="Dall-E (OpenAI)", model_id=None)

    instruct_pix2pix = Img2ImgModel(
        label="✨ InstructPix2Pix (Tim Brooks)", model_id=None
    )
    openjourney_2 = Img2ImgModel(
        label="Open Journey v2 beta (PromptHero) 🐢",
        model_id="prompthero/openjourney-v2",
    )
    openjourney = Img2ImgModel(
        label="Open Journey (PromptHero) 🐢", model_id="prompthero/openjourney"
    )
    analog_diffusion = Img2ImgModel(
        label="Analog Diffusion (wavymulder) 🐢", model_id="wavymulder/Analog-Diffusion"
    )
    protogen_5_3 = Img2ImgModel(
        label="Protogen v5.3 (darkstorm2150) 🐢",
        model_id="darkstorm2150/Protogen_v5.3_Official_Release",
    )

    jack_qiao = Img2ImgModel(
        label="Stable Diffusion v1.4 [Deprecated] (Jack Qiao)", model_id=None
    )
    rodent_diffusion_1_5 = Img2ImgModel(
        label="Rodent Diffusion 1.5 [Deprecated] (NerdyRodent)", model_id=None
    )

    @classmethod
    def _deprecated(cls):
        return {cls.jack_qiao, cls.rodent_diffusion_1_5}


class ControlNetModel(typing.NamedTuple):
    label: str
    model_id: str
    explanation: str


class ControlNetModels(ControlNetModel, GooeyEnum):
    sd_controlnet_canny = ControlNetModel(
        label="Canny",
        explanation="Canny edge detection",
        model_id="lllyasviel/sd-controlnet-canny",
    )
    sd_controlnet_depth = ControlNetModel(
        label="Depth",
        explanation="Depth estimation",
        model_id="lllyasviel/sd-controlnet-depth",
    )
    sd_controlnet_hed = ControlNetModel(
        label="HED Boundary",
        explanation="HED edge detection",
        model_id="lllyasviel/sd-controlnet-hed",
    )
    sd_controlnet_mlsd = ControlNetModel(
        label="M-LSD Straight Line",
        explanation="M-LSD straight line detection",
        model_id="lllyasviel/sd-controlnet-mlsd",
    )
    sd_controlnet_normal = ControlNetModel(
        label="Normal Map",
        explanation="Normal map estimation",
        model_id="lllyasviel/sd-controlnet-normal",
    )
    sd_controlnet_openpose = ControlNetModel(
        label="Human Pose",
        explanation="Human pose estimation",
        model_id="lllyasviel/sd-controlnet-openpose",
    )
    sd_controlnet_scribble = ControlNetModel(
        label="Scribble",
        explanation="Scribble",
        model_id="lllyasviel/sd-controlnet-scribble",
    )
    sd_controlnet_seg = ControlNetModel(
        label="Image Segmentation",
        explanation="Image segmentation",
        model_id="lllyasviel/sd-controlnet-seg",
    )
    sd_controlnet_tile = ControlNetModel(
        label="Tiling",
        explanation="Tiling: to preserve small details",
        model_id="lllyasviel/control_v11f1e_sd15_tile",
    )
    sd_controlnet_brightness = ControlNetModel(
        label="Brightness",
        explanation="Brightness: to increase contrast naturally",
        model_id="ioclab/control_v1p_sd15_brightness",
    )
    control_v1p_sd15_qrcode_monster_v2 = ControlNetModel(
        label="QR Monster V2",
        explanation="QR Monster: make beautiful QR codes that still scan with a controlnet specifically trained for this purpose",
        model_id="monster-labs/control_v1p_sd15_qrcode_monster/v2",
    )


class Scheduler(typing.NamedTuple):
    label: str
    model_id: str


class Schedulers(Scheduler, GooeyEnum):
    singlestep_dpm_solver = Scheduler(
        label="DPM",
        model_id="DPMSolverSinglestepScheduler",
    )
    multistep_dpm_solver = Scheduler(
        label="DPM Multistep", model_id="DPMSolverMultistepScheduler"
    )
    dpm_sde = Scheduler(
        label="DPM SDE",
        model_id="DPMSolverSDEScheduler",
    )
    dpm_discrete = Scheduler(
        label="DPM Discrete",
        model_id="KDPM2DiscreteScheduler",
    )
    dpm_discrete_ancestral = Scheduler(
        label="DPM Anscetral",
        model_id="KDPM2AncestralDiscreteScheduler",
    )
    unipc = Scheduler(label="UniPC", model_id="UniPCMultistepScheduler")
    lms_discrete = Scheduler(
        label="LMS",
        model_id="LMSDiscreteScheduler",
    )
    heun = Scheduler(
        label="Heun",
        model_id="HeunDiscreteScheduler",
    )
    euler = Scheduler("Euler", "EulerDiscreteScheduler")
    euler_ancestral = Scheduler(
        label="Euler ancestral",
        model_id="EulerAncestralDiscreteScheduler",
    )
    pndm = Scheduler(label="PNDM", model_id="PNDMScheduler")
    ddpm = Scheduler(label="DDPM", model_id="DDPMScheduler")
    ddim = Scheduler(label="DDIM", model_id="DDIMScheduler")
    deis = Scheduler(
        label="DEIS",
        model_id="DEISMultistepScheduler",
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
    dall_e_3_quality: str | None = None,
    dall_e_3_style: str | None = None,
):
    if selected_model != Text2ImgModels.dall_e_3.name:
        _resolution_check(width, height, max_size=(1024, 1024))

    match selected_model:
        case Text2ImgModels.dall_e_3.name:
            from openai import OpenAI

            client = OpenAI()
            width, height = _get_dall_e_3_img_size(width, height)
            with capture_openai_content_policy_violation():
                response = client.images.generate(
                    model=Text2ImgModels[selected_model].model_id,
                    n=1,  # num_outputs, not supported yet
                    prompt=prompt,
                    response_format="b64_json",
                    quality=dall_e_3_quality,
                    style=dall_e_3_style,
                    size=f"{width}x{height}",
                )
            out_imgs = [b64_img_decode(part.b64_json) for part in response.data]
        case Text2ImgModels.dall_e.name:
            from openai import OpenAI

            edge = _get_dall_e_img_size(width, height)
            client = OpenAI()
            with capture_openai_content_policy_violation():
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
                    "model_id": Text2ImgModels[selected_model].model_id,
                    "scheduler": Schedulers[scheduler].model_id if scheduler else None,
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


def _get_dall_e_img_size(width: int, height: int) -> int:
    edge = max(width, height)
    if edge < 512:
        edge = 256
    elif 512 < edge < 1024:
        edge = 512
    elif edge > 1024:
        edge = 1024
    return edge


def _get_dall_e_3_img_size(width: int, height: int) -> tuple[int, int]:
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

            edge = _get_dall_e_img_size(width, height)
            image = resize_img_pad(init_image_bytes, (edge, edge))
            image = rgb_img_to_rgba(image)
            mask = io.BytesIO()
            Image.new("RGBA", (edge, edge), (0, 0, 0, 0)).save(mask, format="PNG")
            mask = mask.getvalue()

            client = OpenAI()
            with capture_openai_content_policy_violation():
                response = client.images.edit(
                    model="dall-e-2",
                    prompt=prompt,
                    image=image,
                    mask=mask,
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
                    "model_id": Img2ImgModels[selected_model].model_id,
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
    init_images: list[str] | str,
    num_inference_steps: int = 50,
    negative_prompt: str = None,
    guidance_scale: float = 7.5,
    seed: int = 42,
    controlnet_conditioning_scale: typing.List[float] | float = 1.0,
):
    if isinstance(selected_controlnet_model, str):
        selected_controlnet_model = [selected_controlnet_model]
    if isinstance(init_images, str):
        init_images = [init_images] * len(selected_controlnet_model)
    prompt = add_prompt_prefix(prompt, selected_model)
    return call_sd_multi(
        "diffusion.controlnet",
        pipeline={
            "model_id": Text2ImgModels[selected_model].model_id,
            "seed": seed,
            "scheduler": (
                Schedulers[scheduler].model_id
                if scheduler
                else Schedulers.unipc.model_id
            ),
            "disable_safety_checker": True,
            "controlnet_model_id": [
                ControlNetModels[model].model_id for model in selected_controlnet_model
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
                    "model_id": InpaintingModels[selected_model].model_id,
                    "seed": seed,
                    # "scheduler": Schedulers[scheduler].model_id
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
