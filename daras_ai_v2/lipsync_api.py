from daras_ai_v2.exceptions import UserError
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
