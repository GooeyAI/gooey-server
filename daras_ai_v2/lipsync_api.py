from daras_ai_v2.gpu_server import call_gpu_server_b64, GpuEndpoints


def wav2lip(*, face: str, audio: str, pads: (int, int, int, int)) -> bytes:
    return call_gpu_server_b64(
        endpoint=GpuEndpoints.wav2lip,
        input_data={
            "face": face,
            "audio": audio,
            "pads": " ".join(map(str, pads)),
            # "out_height": 480,
            # "smooth": True,
            # "fps": 25,
        },
    )[0]
