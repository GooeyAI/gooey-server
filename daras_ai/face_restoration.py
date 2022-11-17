from concurrent.futures import ThreadPoolExecutor

import replicate
import streamlit as st

from daras_ai.core import daras_ai_step_config, daras_ai_step_computer
from daras_ai_v2.gpu_server import call_gpu_server_b64, GpuEndpoints


@daras_ai_step_config("Face Restoration")
def face_restoration(idx, variables, state):
    selected_model = st.selectbox("Model", options=["gfpgan"])
    state.update({"selected_model": selected_model})

    img_input_var = st.text_input(
        "Image Input Variable",
        value=state.get("img_input_var", ""),
        help=f"face restoration img input {idx + 1}",
    )
    state.update({"img_input_var": img_input_var})

    img_output_var = st.text_input(
        "Image Output Variable",
        value=state.get("img_output_var", ""),
        help=f"face restoration img output {idx + 1}",
    )
    state.update({"img_output_var": img_output_var})


@daras_ai_step_computer
def face_restoration(idx, variables, state):
    img_input_var = state["img_input_var"]
    img_output_var = state["img_output_var"]
    selected_model = state["selected_model"]
    input_images = variables.get(img_input_var)

    if not (input_images and img_output_var and selected_model):
        return

    if not isinstance(input_images, list):
        input_images = [input_images]

    match selected_model:
        case "gfpgan":
            variables[img_output_var] = map_parallel(gfpgan_replicate, input_images)


def gfpgan_replicate(img: str):
    model = replicate.models.get("tencentarc/gfpgan")
    return model.predict(img=img)


def gfpgan(img: str) -> bytes:
    return call_gpu_server_b64(
        endpoint=GpuEndpoints.gfpgan,
        input_data={
            "img": img,
            "version": "v1.4",
            "scale": 1,
        },
    )[0]


def map_parallel(fn, it):
    with ThreadPoolExecutor(max_workers=len(it)) as pool:
        return list(pool.map(fn, it))
