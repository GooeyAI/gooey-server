from copy import deepcopy
from time import time

import requests
import streamlit as st
from pydantic import BaseModel

from daras_ai.face_restoration import map_parallel, gfpgan
from daras_ai.image_input import (
    resize_img,
    upload_file_from_bytes,
    upload_file,
)
from daras_ai.logo import logo
from daras_ai_v2 import stable_diffusion
from daras_ai_v2.base import get_saved_state, run_as_api_tab, save_button
from daras_ai_v2.extract_face import extract_face_img_bytes

DOC_NAME = "FaceInpainting"
API_URL = "/v1/FaceInpainting/run"


class RequestModel(BaseModel):
    input_photo: str
    text_prompt: str

    num_outputs: int = 1
    quality: int = 50

    class Config:
        schema_extra = {
            "example": {
                "text_prompt": "tony stark from the iron man",
                "input_photo": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/2bcf31e8-48ef-11ed-8fe1-02420a00005c/_DSC0030_1.jpg",
            }
        }


class ResponseModel(BaseModel):
    resized_image: str
    face_mask: str
    output_images: list[str]


def main():
    logo()

    if not st.session_state:
        st.session_state.update(deepcopy(get_saved_state(DOC_NAME)))
    st.session_state.setdefault("num_steps", 50)

    save_button(DOC_NAME)

    tab1, tab2, tab3 = st.tabs(["🏃‍♀️ Run", "⚙️ Settings", "🚀 Run as API"])

    with tab1:
        run_tab()

    with tab2:
        edit_tab()

    with tab3:
        run_as_api_tab(API_URL, RequestModel)


def run_tab():
    st.write(
        """
### You as Superhero

*Face Inpainting: Profile pic > Face Masking > Stable Diffusion > GFPGAN*

Render yourself as superman, iron man, as a pizza, whatever!

How It Works:

1. Extracts faces from any image using MediaPipe
2. Generates images from the given prompt and inpaints with Stable diffusion
3. Improves faces using gfpgan    
"""
    )

    with st.form("my_form"):
        st.write(
            """
            ### Prompt
            Describe the character that you'd like to generate. 
            """
        )
        st.text_input(
            "",
            label_visibility="collapsed",
            key="text_prompt",
            placeholder="Iron man",
        )

        st.write(
            """
            ### Face Photo
            Give us a photo of yourself, or anyone else
            """
        )
        input_file = st.file_uploader(
            "",
            label_visibility="collapsed",
        )
        st.caption(
            "By uploading an image, you agree to Dara's [Privacy Policy](https://dara.network/privacy)"
        )

        col1, col2 = st.columns(2)

        with col1:
            st.slider(label="# of Outputs", key="num_outputs", min_value=1, max_value=4)
        with col2:
            st.slider(
                label="Quality",
                key="num_steps",
                min_value=10,
                max_value=200,
                step=10,
            )

        submitted = st.form_submit_button("🚀 Submit")

    msg_container = st.container()

    text_prompt = st.session_state.get("text_prompt", "")
    input_image_or_file = input_file or st.session_state.get("input_image")

    gen = None
    start = time()
    if submitted:
        if not (text_prompt and input_image_or_file):
            with msg_container:
                st.error("Please provide a Prompt and a Face Photo", icon="⚠️")
        else:
            gen = run(st.session_state)

    final_col1, final_col2 = st.columns(2)
    with final_col1:
        if input_image_or_file:
            st.image(input_image_or_file, caption="Face Photo")

    with st.expander("Steps", expanded=True):
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            if input_image_or_file:
                st.image(input_image_or_file, caption="Input Image")

        with col2:
            if gen:
                with st.spinner():
                    if input_file:
                        st.session_state["input_image"] = upload_file(input_file)
                    next(gen)
            if "resized_image" in st.session_state:
                st.image(st.session_state["resized_image"], caption="Cropped Image")
            if "face_mask" in st.session_state:
                st.image(st.session_state["face_mask"], caption="Face Mask")

        with col3:
            if gen:
                with st.spinner():
                    next(gen)
            if "diffusion_images" in st.session_state:
                for url in st.session_state["diffusion_images"]:
                    st.image(url, caption=f"Stable Diffusion - “{text_prompt}”")

        with col4:
            if gen:
                with st.spinner():
                    next(gen)
            if "output_images" in st.session_state:
                for url in st.session_state["output_images"]:
                    st.image(url, caption="gfpgan (Face Restoration)")

        if gen:
            time_taken = time() - start
            with msg_container:
                st.success(
                    f"Success! Run Time: `{time_taken:.1f}` seconds. "
                    f"This GPU time is free while we're building daras.ai, Enjoy!",
                    icon="✅",
                )

    with final_col2:
        if "output_images" in st.session_state:
            for url in st.session_state["output_images"]:
                st.image(url, caption=f"“{text_prompt}”")


def edit_tab():
    pass


def run(state: dict):
    img_bytes = requests.get(state["input_image"]).content

    re_img_bytes = resize_img(img_bytes, (512, 512))
    re_img_bytes, face_mask_bytes = extract_face_img_bytes(re_img_bytes)

    state["resized_image"] = upload_file_from_bytes("re_img.png", re_img_bytes)
    state["face_mask"] = upload_file_from_bytes("face_mask.png", face_mask_bytes)

    yield

    output_images = stable_diffusion.inpainting(
        prompt=state.get("text_prompt", ""),
        num_outputs=state.get("num_outputs", 1),
        edit_image=state["resized_image"],
        mask=state["face_mask"],
        num_inference_steps=state.get("num_steps", 50),
    )

    state["diffusion_images"] = [
        upload_file_from_bytes("diffusion.png", requests.get(url).content)
        for url in output_images
    ]

    yield

    output_images = map_parallel(gfpgan, output_images)

    state["output_images"] = [
        upload_file_from_bytes("out.png", requests.get(url).content)
        for url in output_images
    ]

    yield


if __name__ == "__main__":
    main()
