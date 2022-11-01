import cv2
import requests
import streamlit as st
from pydantic import BaseModel

from daras_ai.face_restoration import map_parallel, gfpgan
from daras_ai.image_input import (
    resize_img,
    upload_file_from_bytes,
    upload_file,
    cv2_img_to_png,
    bytes_to_cv2_img,
)
from daras_ai_v2 import stable_diffusion
from daras_ai_v2.base import DarsAiPage
from daras_ai_v2.extract_face import extract_face_img_bytes


class FaceInpaintingPage(DarsAiPage):
    doc_name = "FaceInpainting#2"
    endpoint = "/v1/FaceInpainting/run"

    class RequestModel(BaseModel):
        input_image: str
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
        diffusion_images: list[str]
        output_images: list[str]

    def __init__(self):
        st.session_state.setdefault("num_steps", 50)

    def render_title(self):
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

    def render_form(self):
        with st.form("my_form"):
            st.write(
                """
                ### Prompt
                Describe the character that you'd like to generate. 
                """
            )
            st.text_input(
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
                "By uploading an image, you agree to Dara's [Privacy Policy](https://dara.network/privacy)"
            )

            col1, col2 = st.columns(2)

            with col1:
                st.slider(
                    label="# of Outputs",
                    key="num_outputs",
                    min_value=1,
                    max_value=4,
                )
            with col2:
                st.slider(
                    label="Quality",
                    key="num_steps",
                    min_value=10,
                    max_value=200,
                    step=10,
                )

            submitted = st.form_submit_button("🚀 Submit")

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
            if input_file:
                st.session_state["input_image"] = upload_file(input_file)

        return submitted

    def render_settings(self):
        pass

    def render_output(self):
        text_prompt = st.session_state.get("text_prompt", "")
        input_file = st.session_state.get("input_file")
        input_image = st.session_state.get("input_image")
        input_image_or_file = input_file or input_image
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

        with st.expander("Steps"):
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

        re_img_bytes = resize_img(img_bytes, (512, 512))
        re_img_bytes, face_mask_bytes = extract_face_img_bytes(re_img_bytes)

        state["resized_image"] = upload_file_from_bytes("re_img.png", re_img_bytes)
        state["face_mask"] = upload_file_from_bytes("face_mask.png", face_mask_bytes)

        yield "Running Stable Diffusion..."

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

        yield "Running gfpgan..."

        output_images = map_parallel(gfpgan, output_images)

        state["output_images"] = [
            upload_file_from_bytes("out.png", requests.get(url).content)
            for url in output_images
        ]

        state["output_images"] = self.add_watermark_to_images(output_images)

    # FIXME: Maybe move the function somewhere else.
    def add_watermark_to_images(self, output_images):
        output_images_with_watermark = []
        url_logo = "https://static.wixstatic.com/media/07c536_57cbebd88cab4899b914a739df226e7e~mv2.png/v1/fill/w_276,h_91,al_c,q_85,usm_0.66_1.00_0.01,enc_auto/Screenshot%202022-09-27%20at%2010_57_07%20PM.png"
        for url in output_images:
            img_bytes = requests.get(url).content
            logo_bytes = requests.get(url_logo).content
            img = bytes_to_cv2_img(img_bytes)
            logo = bytes_to_cv2_img(logo_bytes)
            # height and width of the logo
            h_logo, w_logo, _ = logo.shape

            # height and width of the image
            h_img, w_img, _ = img.shape
            # place our watermark
            center_y = int(h_img)
            center_x = int(w_img)
            # calculating from top, bottom, right and left
            top_y = center_y - int(h_logo)
            left_x = center_x - int(w_logo)
            bottom_y = top_y + h_logo
            right_x = left_x + w_logo
            # adding watermark to the image
            destination = img[top_y:bottom_y, left_x:right_x]
            result = cv2.addWeighted(destination, 1, logo, 0.4, 0)
            img[top_y:bottom_y, left_x:right_x] = result
            updated_url = upload_file_from_bytes("out.png", cv2_img_to_png(img))
            output_images_with_watermark.append(updated_url)
        return output_images_with_watermark

    def render_example(self, state: dict):
        col1, col2 = st.columns(2)
        with col1:
            input_image = state.get("input_image")
            if input_image:
                st.image(input_image)
        with col2:
            output_images = state.get("output_images")
            if output_images:
                for img in output_images:
                    st.image(img)


if __name__ == "__main__":
    FaceInpaintingPage().render()
