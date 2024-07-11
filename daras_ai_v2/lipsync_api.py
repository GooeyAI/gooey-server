import typing
from enum import Enum

from loguru import logger
from pydantic import BaseModel, Field

from daras_ai_v2.exceptions import UserError, GPUError
from daras_ai_v2.gpu_server import call_celery_task_outfile
from daras_ai_v2.pydantic_validation import FieldHttpUrl


class LipsyncModel(Enum):
    Wav2Lip = "Rudrabha/Wav2Lip"
    SadTalker = "OpenTalker/SadTalker"


class SadTalkerSettings(BaseModel):
    still: bool = Field(
        True, title="Still (fewer head motion, works with preprocess 'full')"
    )
    preprocess: typing.Literal["crop", "extcrop", "resize", "full", "extfull"] = Field(
        "resize",
        title="Preprocess",
        description="SadTalker only generates 512x512 output. 'crop' handles this by cropping the input to 512x512. 'resize' scales down the input to fit 512x512 and scales it back up after lipsyncing (does not work well for full person images, better for portraits). 'full' processes the cropped region and pastes it back into the original input. 'extcrop' and 'extfull' are similar to 'crop' and 'full' but with extended cropping.",
    )
    pose_style: int = Field(
        0,
        title="Pose Style",
        description="Random seed 0-45 inclusive that affects how the pose is animated.",
    )
    expression_scale: float = Field(
        1.0,
        title="Expression Scale",
        description="Scale the amount of expression motion. 1.0 is normal, 0.5 is very reduced, and 2.0 is quite a lot.",
    )
    ref_eyeblink: FieldHttpUrl = Field(
        None,
        title="Reference Eyeblink",
        description="Optional reference video for eyeblinks to make the eyebrow movement more natural.",
    )
    ref_pose: FieldHttpUrl = Field(
        None,
        title="Reference Pose",
        description="Optional reference video to pose the head.",
    )
    # enhancer: typing.Literal["gfpgan", "RestoreFormer"] =None
    # background_enhancer: typing.Literal["realesrgan"] =None
    input_yaw: list[int] = Field(
        None, title="Input Yaw (comma separated)", deprecated=True
    )
    input_pitch: list[int] = Field(
        None, title="Input Pitch (comma separated)", deprecated=True
    )
    input_roll: list[int] = Field(
        None, title="Input Roll (comma separated)", deprecated=True
    )


class LipsyncSettings(BaseModel):
    input_face: FieldHttpUrl = None

    # wav2lip
    face_padding_top: int = None
    face_padding_bottom: int = None
    face_padding_left: int = None
    face_padding_right: int = None

    sadtalker_settings: SadTalkerSettings = None


def run_sadtalker(settings: SadTalkerSettings, face: str, audio: str):
    return call_celery_task_outfile(
        "lipsync.sadtalker",
        pipeline=dict(
            model_id="SadTalker_V0.0.2_512.safetensors",
            preprocess=settings.preprocess,
        ),
        inputs=settings.dict() | dict(source_image=face, driven_audio=audio),
        content_type="video/mp4",
        filename=f"gooey.ai lipsync.mp4",
    )[0]


def run_wav2lip(*, face: str, audio: str, pads: tuple[int, int, int, int]) -> bytes:
    try:
        return call_celery_task_outfile(
            "wav2lip",
            pipeline=dict(
                model_id="wav2lip_gan.pth",
            ),
            inputs=dict(
                face=face,
                audio=audio,
                pads=pads,
                batch_size=256,
                # "out_height": 480,
                # "smooth": True,
                # "fps": 25,
            ),
            content_type="video/mp4",
            filename=f"gooey.ai lipsync.mp4",
        )[0]
    except ValueError as e:
        msg = "\n\n".join(e.args).lower()
        if "unsupported" in msg:
            raise UserError(msg) from e
        else:
            raise
    except GPUError as e:
        if "ffmpeg" in e.message and "Command" in e.message:
            logger.exception(f"ffmpeg error: {str(e)}")
            raise GPUError(
                f"""\
It seems like you are not using a human face for the input. This AI tool requires \
a human face to run the lipsync workflow. Know more [here](https://gooey.ai/docs/guides/lip-sync-animation-generator#id-3akkpf7ao60t). \


Details:

{e.message}
"""
            )
        else:
            raise
