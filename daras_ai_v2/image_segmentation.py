from daras_ai.image_input import bytes_to_cv2_img, cv2_img_to_bytes
from daras_ai_v2.gpu_server import call_gpu_server_b64, GpuEndpoints


def u2net(input_image: str) -> bytes:
    return call_gpu_server_b64(
        endpoint=GpuEndpoints.u2net,
        input_data={
            "image": input_image,
        },
    )[0]


def dis(input_image: str) -> bytes:
    return call_gpu_server_b64(
        endpoint=GpuEndpoints.dichotomous_image_segmentation,
        input_data={
            "input_image": input_image,
        },
    )[0]
