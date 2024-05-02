import typing
from enum import Enum

from loguru import logger
from pydantic import HttpUrl, BaseModel, Field

from daras_ai_v2.exceptions import UserError, GPUError
from daras_ai_v2.gpu_server import call_celery_task_outfile


class LipsyncModel(Enum):
    Wav2Lip = "Rudrabha/Wav2Lip"
    SadTalker = "OpenTalker/SadTalker"


class SadTalkerSettings(BaseModel):
    still: bool = Field(
        False, title="Still (fewer head motion, works with preprocess 'full')"
    )
    preprocess: typing.Literal["crop", "extcrop", "resize", "full", "extfull"] = Field(
        "crop", title="Preprocess"
    )
    pose_style: int = Field(0, title="Pose Style")
    expression_scale: float = Field(1.0, title="Expression Scale")
    ref_eyeblink: HttpUrl = Field(None, title="Reference Eyeblink")
    ref_pose: HttpUrl = Field(None, title="Reference Pose")
    input_yaw: list[int] = Field(None, title="Input Yaw (comma separated)")
    input_pitch: list[int] = Field(None, title="Input Pitch (comma separated)")
    input_roll: list[int] = Field(None, title="Input Roll (comma separated)")
    # enhancer: typing.Literal["gfpgan", "RestoreFormer"] =None
    # background_enhancer: typing.Literal["realesrgan"] =None


class LipsyncSettings(BaseModel):
    input_face: HttpUrl = None

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
