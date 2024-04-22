from loguru import logger

from daras_ai_v2.exceptions import UserError, GPUError
from daras_ai_v2.gpu_server import call_celery_task_outfile

from pydantic import BaseModel, HttpUrl
import typing


class SadtalkerInput(BaseModel):
    source_image: HttpUrl
    driven_audio: HttpUrl
    pose_style: int
    ref_eyeblink: HttpUrl | None = None
    ref_pose: HttpUrl | None = None
    batch_size: int = 2
    size: int = 256
    expression_scale: float = 1.0
    input_yaw: list[int] | None = None
    input_pitch: list[int] | None = None
    input_roll: list[int] | None = None
    enhancer: typing.Literal["gfpgan", "RestoreFormer"] | None = None
    background_enhancer: typing.Literal["realesrgan"] | None = None
    face3dvis: bool = False
    still: bool = False
    preprocess: typing.Literal["crop", "extcrop", "resize", "full", "extfull"] = "crop"


def sadtalker(input: SadtalkerInput):
    return call_celery_task_outfile(
        "lipsync.sadtalker",
        pipeline=dict(model_id="sadtalker"),
        inputs=input.dict(),
        content_type="video/mp4",
        filename=f"gooey.ai lipsync.mp4",
    )[0]


def wav2lip(*, face: str, audio: str, pads: tuple[int, int, int, int]) -> bytes:
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
