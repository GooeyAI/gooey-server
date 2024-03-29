from loguru import logger

from daras_ai_v2.exceptions import UserError, GPUError
from daras_ai_v2.gpu_server import call_celery_task_outfile


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
