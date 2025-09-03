from enum import Enum
import typing

import requests
import json
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.gpu_server import call_celery_task_outfile
from daras_ai_v2.pydantic_validation import OptionalHttpUrlStr


class VideoGenerationModels(Enum):
    fal_wan_v2_2_turbo = "FAL wan v2.2 turbo"
    openai_sora = "Sora (OpenAI) - Coming Soon"
    google_veo_3 = "Veo 3 (Google) - Coming Soon"
    runway_gen_3 = "Runway Gen-3 - Coming Soon"
    pika_labs = "Pika Labs - Coming Soon"

    @classmethod
    def _deprecated(cls):
        return set()


# Model ID mappings for API calls
video_model_ids = {
    VideoGenerationModels.fal_wan_v2_2_turbo: "fal-ai/wan/v2.2-a14b/image-to-video/turbo",
    VideoGenerationModels.openai_sora: "sora-1.0-turbo",
    VideoGenerationModels.google_veo_3: "veo-3",
    VideoGenerationModels.runway_gen_3: "runway-gen3",
    VideoGenerationModels.pika_labs: "pika-1.0",
}


def generate_video(
    *,
    model: VideoGenerationModels,
    prompt: str,
    duration: int = 8,
    reference_image: str = None,
    aspect_ratio: str = "16:9",
    resolution: str = "1080p",
    frames_per_second: int = 30,
    style: str = None,
    negative_prompt: str = None,
    seed: int = None,
) -> typing.Generator[str, None, OptionalHttpUrlStr]:
    """
    Generate a video using the specified model and parameters.

    Args:
        model: The video generation model to use
        prompt: Text description of the video to generate
        duration: Duration of video in seconds (3-30)
        reference_image: Optional reference image URL for style/subject
        aspect_ratio: Video aspect ratio (16:9, 9:16, 1:1)
        resolution: Video resolution (480p, 580p, 720p, 1080p, 4K)
        frames_per_second: Video frame rate (24, 30, 60)
        style: Optional style parameter
        negative_prompt: What to avoid in the video
        seed: Random seed for reproducibility

    Returns:
        URL of the generated video
    """

    match model:
        case VideoGenerationModels.fal_wan_v2_2_turbo:
            return (
                yield from _generate_fal_wan_video(
                    prompt=prompt,
                    duration=duration,
                    reference_image=reference_image,
                    aspect_ratio=aspect_ratio,
                    resolution=resolution,
                    frames_per_second=frames_per_second,
                    style=style,
                    negative_prompt=negative_prompt,
                    seed=seed,
                )
            )
        case VideoGenerationModels.openai_sora:
            return _generate_sora_video(
                prompt=prompt,
                duration=duration,
                reference_image=reference_image,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                frames_per_second=frames_per_second,
                seed=seed,
            )
        case VideoGenerationModels.google_veo_3:
            return _generate_veo3_video(
                prompt=prompt,
                duration=duration,
                reference_image=reference_image,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                frames_per_second=frames_per_second,
                seed=seed,
            )
        case VideoGenerationModels.runway_gen_3:
            return _generate_runway_video(
                prompt=prompt,
                duration=duration,
                reference_image=reference_image,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                frames_per_second=frames_per_second,
                seed=seed,
            )
        case VideoGenerationModels.pika_labs:
            return _generate_pika_video(
                prompt=prompt,
                duration=duration,
                reference_image=reference_image,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                frames_per_second=frames_per_second,
                negative_prompt=negative_prompt,
                seed=seed,
            )
        case _:
            raise UserError(f"Unsupported video generation model: {model}")


def _generate_sora_video(
    prompt: str,
    duration: int,
    reference_image: str = None,
    aspect_ratio: str = "16:9",
    resolution: str = "1080p",
    frames_per_second: int = 30,
    seed: int = None,
) -> OptionalHttpUrlStr:
    """Generate video using OpenAI Sora"""
    return call_celery_task_outfile(
        "sora_video_generation",
        pipeline=dict(
            model_id=video_model_ids[VideoGenerationModels.openai_sora],
            resolution=resolution,
            frames_per_second=frames_per_second,
        ),
        inputs=dict(
            prompt=prompt,
            duration=duration,
            reference_image=reference_image,
            aspect_ratio=aspect_ratio,
            seed=seed,
        ),
        content_type="video/mp4",
        filename=f"sora_video_{prompt[:50]}.mp4",
    )[0]


def _generate_veo3_video(
    prompt: str,
    duration: int,
    reference_image: str = None,
    aspect_ratio: str = "16:9",
    resolution: str = "1080p",
    frames_per_second: int = 30,
    seed: int = None,
) -> OptionalHttpUrlStr:
    """Generate video using Google Veo 3"""
    return call_celery_task_outfile(
        "veo3_video_generation",
        pipeline=dict(
            model_id=video_model_ids[VideoGenerationModels.google_veo_3],
            resolution=resolution,
            frames_per_second=frames_per_second,
        ),
        inputs=dict(
            prompt=prompt,
            duration=duration,
            reference_image=reference_image,
            aspect_ratio=aspect_ratio,
            seed=seed,
        ),
        content_type="video/mp4",
        filename=f"veo3_video_{prompt[:50]}.mp4",
    )[0]


def _generate_runway_video(
    prompt: str,
    duration: int,
    reference_image: str = None,
    aspect_ratio: str = "16:9",
    resolution: str = "1080p",
    frames_per_second: int = 30,
    seed: int = None,
) -> OptionalHttpUrlStr:
    """Generate video using Runway Gen-3"""
    return call_celery_task_outfile(
        "runway_video_generation",
        pipeline=dict(
            model_id=video_model_ids[VideoGenerationModels.runway_gen_3],
            resolution=resolution,
            frames_per_second=frames_per_second,
        ),
        inputs=dict(
            prompt=prompt,
            duration=duration,
            reference_image=reference_image,
            aspect_ratio=aspect_ratio,
            seed=seed,
        ),
        content_type="video/mp4",
        filename=f"runway_video_{prompt[:50]}.mp4",
    )[0]


def _generate_pika_video(
    prompt: str,
    duration: int,
    reference_image: str = None,
    aspect_ratio: str = "16:9",
    resolution: str = "1080p",
    frames_per_second: int = 30,
    negative_prompt: str = None,
    seed: int = None,
) -> OptionalHttpUrlStr:
    """Generate video using Pika Labs"""
    return call_celery_task_outfile(
        "pika_video_generation",
        pipeline=dict(
            model_id=video_model_ids[VideoGenerationModels.pika_labs],
            resolution=resolution,
            frames_per_second=frames_per_second,
        ),
        inputs=dict(
            prompt=prompt,
            duration=duration,
            reference_image=reference_image,
            aspect_ratio=aspect_ratio,
            negative_prompt=negative_prompt,
            seed=seed,
        ),
        content_type="video/mp4",
        filename=f"pika_video_{prompt[:50]}.mp4",
    )[0]


def _generate_fal_wan_video(
    prompt: str,
    duration: int,
    reference_image: str = None,
    aspect_ratio: str = "16:9",
    resolution: str = "1080p",
    frames_per_second: int = 30,
    style: str = None,
    negative_prompt: str = None,
    seed: int = None,
) -> typing.Generator[str, None, OptionalHttpUrlStr]:
    """Generate video using FAL wan v2.2 turbo"""
    from daras_ai_v2.fal_ai import generate_on_fal

    # Build payload for FAL API
    payload = dict(
        prompt=prompt,
        duration=duration,
    )

    # Add image parameter only if reference image is provided
    if reference_image:
        payload["image_url"] = reference_image

    if style:
        payload["style"] = style
    if negative_prompt:
        payload["negative_prompt"] = negative_prompt
    if seed:
        payload["seed"] = seed

    # Convert resolution and aspect ratio to dimensions
    # FAL expects width and height parameters
    if aspect_ratio == "16:9":
        if resolution == "480p":
            payload["width"] = 854
            payload["height"] = 480
        elif resolution == "580p":
            payload["width"] = 1032
            payload["height"] = 580
        elif resolution == "720p":
            payload["width"] = 1280
            payload["height"] = 720
        elif resolution == "1080p":
            payload["width"] = 1920
            payload["height"] = 1080
        elif resolution == "4K":
            payload["width"] = 3840
            payload["height"] = 2160
    elif aspect_ratio == "9:16":
        if resolution == "480p":
            payload["width"] = 480
            payload["height"] = 854
        elif resolution == "580p":
            payload["width"] = 580
            payload["height"] = 1032
        elif resolution == "720p":
            payload["width"] = 720
            payload["height"] = 1280
        elif resolution == "1080p":
            payload["width"] = 1080
            payload["height"] = 1920
    elif aspect_ratio == "1:1":
        if resolution == "480p":
            payload["width"] = 480
            payload["height"] = 480
        elif resolution == "580p":
            payload["width"] = 580
            payload["height"] = 580
        elif resolution == "720p":
            payload["width"] = 720
            payload["height"] = 720
        elif resolution == "1080p":
            payload["width"] = 1080
            payload["height"] = 1080

    # Call FAL API directly (with streaming)
    result = yield from generate_on_fal(
        model_id=video_model_ids[VideoGenerationModels.fal_wan_v2_2_turbo],
        payload=payload,
    )

    # Record cost for usage tracking
    from usage_costs.cost_utils import record_cost_auto
    from usage_costs.models import ModelSku

    record_cost_auto(
        model=video_model_ids[VideoGenerationModels.fal_wan_v2_2_turbo],
        sku=ModelSku.video_generation,
        quantity=1,  # 1 video generated
    )

    # Extract video URL from result
    if "video" in result and "url" in result["video"]:
        return result["video"]["url"]
    elif "url" in result:
        return result["url"]
    else:
        raise UserError("No video URL in FAL response")
