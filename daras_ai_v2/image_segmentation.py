from daras_ai_v2.gpu_server import call_gpu_server_b64, GpuEndpoints


def dichotomous_image_segmentation(input_image: str) -> bytes:
    return call_gpu_server_b64(
        endpoint=GpuEndpoints.dichotomous_image_segmentation,
        input_data={
            "input_image": input_image,
        },
    )[0]
