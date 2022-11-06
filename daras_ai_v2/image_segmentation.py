from daras_ai_v2.gpu_server import call_gpu_server_b64


def dichotomous_image_segmentation(input_image: str) -> bytes:
    return call_gpu_server_b64(
        port=5004,
        input_data={
            "input_image": input_image,
        },
    )[0]
