import cv2
import requests
import streamlit as st
import typing
from pydantic import BaseModel

import daras_ai.db
import daras_ai_v2.settings
from daras_ai.extract_face import extract_and_reposition_face_cv2
from daras_ai_v2.face_restoration import map_parallel, gfpgan
from daras_ai.image_input import (
    upload_file_from_bytes,
    safe_filename,
    upload_file_hq,
)
from daras_ai_v2 import stable_diffusion
from daras_ai_v2.base import BasePage
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.extract_face import extract_face_img_bytes
from daras_ai_v2.stable_diffusion import InpaintingModels


class FaceInpaintingPage(BasePage):
    title = "A Face in Any Scene"
    slug = "FaceInpainting"
    version = 2

    class RequestModel(BaseModel):
        input_image: str
        text_prompt: str

        num_outputs: int | None
        quality: int | None

        face_scale: float | None
        face_pos_x: float | None
        face_pos_y: float | None

        output_width: int | None
        output_height: int | None

        selected_model: typing.Literal[tuple(e.name for e in InpaintingModels)] | None

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
        diffusion_images: list[str]
        output_images: list[str]

    def preview_description(self) -> str:
        return "This recipe takes a photo with a face and then uses the text prompt to paint a background."

    def render_description(self):
        st.write(
            """    
    This recipe takes a photo with a face and then uses the text prompt to paint a background.
    
    How It Works:
    
    1. Extracts faces from any image using MediaPipe
    2. Generates images from the given prompt and paints a background scene with Stable diffusion
    3. Improves faces using GFPGAN    
    
    *Face Inpainting: Photo > Face Masking > Stable Diffusion > GFPGAN*

    """
        )

    def render_form(self):
        with st.form("my_form"):
            st.write(
                """
                ### Prompt
                Describe the character that you'd like to generate. 
                """
            )
            st.text_area(
                "text_prompt",
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
            st.file_uploader(
                "input_file",
                label_visibility="collapsed",
                key="input_file",
            )
            st.caption(
                "By uploading an image, you agree to Gooey.AI's [Privacy Policy](https://dara.network/privacy)"
            )

            submitted = st.form_submit_button("🏃‍ Submit")

        text_prompt = st.session_state.get("text_prompt")
        input_file = st.session_state.get("input_file")
        input_image = st.session_state.get("input_image")
        input_image_or_file = input_file or input_image

        # form validation
        if submitted and not (text_prompt and input_image_or_file):
            st.error("Please provide a Prompt and a Face Photo", icon="⚠️")
            return False

        # upload input file if submitted
        if submitted:
            input_file = st.session_state.get("input_file")
            deduct_success = super(FaceInpaintingPage, self).deduct_credits()
            if not deduct_success:
                return False
            if input_file:
                st.session_state["input_image"] = upload_file_hq(input_file)

        return submitted

    def render_settings(self):
        selected_model = enum_selector(
            InpaintingModels,
            label="Image Model",
            key="selected_model",
        )

        col1, col2 = st.columns(2, gap="medium")
        with col1:
            st.slider(
                label="# of Outputs",
                key="num_outputs",
                min_value=1,
                max_value=4,
            )
        with col2:
            if selected_model != InpaintingModels.dall_e.name:
                st.slider(
                    label="Quality",
                    key="quality",
                    value=50,
                    min_value=10,
                    max_value=200,
                    step=10,
                )
            else:
                st.empty()

        st.write(
            """
            ### Output Resolution
            """
        )
        col1, col2, col3 = st.columns([10, 1, 10])
        with col1:
            output_width = st.slider(
                "Width",
                key="output_width",
                min_value=512,
                max_value=768,
                step=64,
            )
        with col2:
            st.write("X")
        with col3:
            output_height = st.slider(
                "Height",
                key="output_height",
                min_value=512,
                max_value=768,
                step=64,
            )

        st.write(
            """
            ### Face Repositioning Settings
            """
        )

        st.write("How _big_ should the face look?")
        col1, _ = st.columns(2)
        with col1:
            face_scale = st.slider(
                "Scale",
                min_value=0.1,
                max_value=1.0,
                key="face_scale",
            )

        st.write("_Where_ would you like to place the face in the scene?")
        col1, col2 = st.columns(2)
        with col1:
            pos_x = st.slider(
                "Position X",
                min_value=0.0,
                max_value=1.0,
                key="face_pos_x",
            )
        with col2:
            pos_y = st.slider(
                "Position Y",
                min_value=0.0,
                max_value=1.0,
                key="face_pos_y",
            )

        # show an example image
        img_cv2 = cv2.imread("static/face.png")

        # extract face
        img, mask = extract_and_reposition_face_cv2(
            img_cv2,
            out_size=(output_width, output_height),
            out_face_scale=face_scale,
            out_pos_x=pos_x,
            out_pos_y=pos_y,
        )

        # draw rule of 3rds
        color = (200, 200, 200)
        stroke = 2
        img_y, img_x, _ = img.shape
        for i in range(2):
            pos = (img_y // 3) * (i + 1)
            cv2.line(img, (0, pos), (img_x, pos), color, stroke)

            pos = (img_x // 3) * (i + 1)
            cv2.line(img, (pos, 0), (pos, img_y), color, stroke)

        st.image(img, width=300)

    def render_output(self):
        text_prompt = st.session_state.get("text_prompt", "")
        input_file = st.session_state.get("input_file")
        input_image = st.session_state.get("input_image")
        input_image_or_file = input_image or input_file
        output_images = st.session_state.get("output_images")

        col1, col2 = st.columns(2)

        with col1:
            if input_image_or_file:
                st.image(input_image_or_file, caption="Face Photo")
            else:
                st.empty()

        with col2:
            if output_images:
                for url in output_images:
                    st.image(url, caption=f"“{text_prompt}”")
            else:
                st.empty()

        with st.expander("Steps", expanded=True):
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                if input_image_or_file:
                    st.image(input_image_or_file, caption="Input Image")
                else:
                    st.empty()

            with col2:
                resized_image = st.session_state.get("resized_image")
                if resized_image:
                    st.image(resized_image, caption="Repositioned Face")
                else:
                    st.empty()

                face_mask = st.session_state.get("face_mask")
                if face_mask:
                    st.image(face_mask, caption="Face Mask")
                else:
                    st.empty()

            with col3:
                diffusion_images = st.session_state.get("diffusion_images")
                if diffusion_images:
                    for url in diffusion_images:
                        st.image(url, caption=f"Stable Diffusion - “{text_prompt}”")
                else:
                    st.empty()

            with col4:
                if output_images:
                    for url in output_images:
                        st.image(url, caption="gfpgan - Face Restoration")
                else:
                    st.empty()

    def run(self, state: dict):
        yield "Extracting Face..."

        input_image_url = state["input_image"]
        img_bytes = requests.get(input_image_url).content

        re_img_bytes, face_mask_bytes = extract_face_img_bytes(
            img_bytes,
            out_size=(state["output_width"], state["output_height"]),
            face_scale=state["face_scale"],
            pos_x=state["face_pos_x"],
            pos_y=state["face_pos_y"],
        )

        state["resized_image"] = upload_file_from_bytes("re_img.png", re_img_bytes)
        state["face_mask"] = upload_file_from_bytes("face_mask.png", face_mask_bytes)

        yield f"Generating Image..."

        prompt = state.get("text_prompt", "")

        diffusion_images = stable_diffusion.inpainting(
            selected_model=state["selected_model"],
            prompt=prompt,
            num_outputs=state.get("num_outputs", 1),
            edit_image=state["resized_image"],
            edit_image_bytes=re_img_bytes,
            mask=state["face_mask"],
            mask_bytes=face_mask_bytes,
            num_inference_steps=state.get("quality", 50),
            width=state["output_width"],
            height=state["output_height"],
        )
        state["diffusion_images"] = diffusion_images

        yield "Running gfpgan..."

        output_images = map_parallel(gfpgan, diffusion_images)

        state["output_images"] = [
            upload_file_from_bytes(
                safe_filename(f"gooey.ai inpainting - {prompt.strip()}.png"),
                img_bytes,
                # requests.get(url).content,
            )
            for img_bytes in output_images
        ]

    def render_example(self, state: dict):
        col1, col2 = st.columns(2)
        with col1:
            input_image = state.get("input_image")
            if input_image:
                st.image(input_image, caption="Input Image")
        with col2:
            output_images = state.get("output_images")
            if output_images:
                for img in output_images:
                    st.image(img, caption=state.get("text_prompt", ""))

    def preview_image(self, state: dict) -> str:
        return state.get("output_images", [""])[0]


if __name__ == "__main__":
    FaceInpaintingPage().render()
