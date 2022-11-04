from daras_ai_v2.gpu_server import call_gpu_server_b64

WAV2LIP_PORT = 5001


def wav2lip(*, face: str, audio: str, pads: (int, int, int, int)) -> bytes:
    return call_gpu_server_b64(
        port=WAV2LIP_PORT,
        input_data={
            "face": face,
            "audio": audio,
            "pads": " ".join(map(str, pads)),
            # "out_height": 480,
            # "smooth": True,
            # "fps": 25,
        },
    )[0]
