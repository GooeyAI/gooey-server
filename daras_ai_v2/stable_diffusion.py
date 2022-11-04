from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.gpu_server import call_gpu_server_b64

GLID_3_XL_PORT = 5002


def inpainting(
    *,
    prompt: str,
    num_outputs: int,
    edit_image: str,
    mask: str,
    num_inference_steps: int,
    width: int,
    height: int,
) -> list[str]:
    out_imgs = call_gpu_server_b64(
        port=GLID_3_XL_PORT,
        input_data={
            "prompt": prompt,
            "num_inference_steps": num_inference_steps,
            # "init_image": "string",
            "edit_image": edit_image,
            "mask": mask,
            "num_outputs": num_outputs,
            # "negative_prompt": "string",
            # "outpaint": "expand",
            # "skip_timesteps": 0,
            "width": width,
            "height": height,
        },
    )
    return [
        upload_file_from_bytes("diffusion.png", sd_img_bytes)
        for sd_img_bytes in out_imgs
    ]
