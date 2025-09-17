from enum import Enum
import typing

import requests
import json
from daras_ai_v2.exceptions import UserError
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
    # Input validation
    if not (3 <= duration <= 30):
        raise UserError(
            f"Invalid duration: {duration}. Duration must be between 3 and 30 seconds inclusive."
        )

    valid_aspect_ratios = {"16:9", "9:16", "1:1"}
    if aspect_ratio not in valid_aspect_ratios:
        raise UserError(
            f"Invalid aspect_ratio: {aspect_ratio}. Must be one of {sorted(valid_aspect_ratios)}."
        )

    valid_resolutions = {"480p", "580p", "720p", "1080p", "4K"}
    if resolution not in valid_resolutions:
        raise UserError(
            f"Invalid resolution: {resolution}. Must be one of {sorted(valid_resolutions)}."
        )

    valid_frames_per_second = {24, 30, 60}
    if frames_per_second not in valid_frames_per_second:
        raise UserError(
            f"Invalid frames_per_second: {frames_per_second}. Must be one of {sorted(valid_frames_per_second)}."
        )

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
        case _:
            raise UserError(f"Unsupported video generation model: {model}")


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
    if seed is not None:
        payload["seed"] = seed

    # Convert resolution and aspect ratio to dimensions
    # FAL expects width and height parameters
    dimension_mapping = {
        ("16:9", "480p"): (854, 480),
        ("16:9", "580p"): (1032, 580),
        ("16:9", "720p"): (1280, 720),
        ("16:9", "1080p"): (1920, 1080),
        ("16:9", "4K"): (3840, 2160),
        ("9:16", "480p"): (480, 854),
        ("9:16", "580p"): (580, 1032),
        ("9:16", "720p"): (720, 1280),
        ("9:16", "1080p"): (1080, 1920),
        ("9:16", "4K"): (2160, 3840),
        ("1:1", "480p"): (480, 480),
        ("1:1", "580p"): (580, 580),
        ("1:1", "720p"): (720, 720),
        ("1:1", "1080p"): (1080, 1080),
        ("1:1", "4K"): (3840, 3840),
    }

    # Validate and set dimensions
    dimension_key = (aspect_ratio, resolution)
    if dimension_key not in dimension_mapping:
        raise UserError(
            f"Unsupported combination: aspect_ratio={aspect_ratio}, resolution={resolution}. "
            f"Supported combinations: {sorted(dimension_mapping.keys())}"
        )

    width, height = dimension_mapping[dimension_key]
    payload["width"] = width
    payload["height"] = height

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
