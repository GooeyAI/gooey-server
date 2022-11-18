import cv2
import requests
import streamlit as st
from pydantic import BaseModel

from daras_ai.image_input import (
    upload_file_from_bytes,
    upload_file_hq,
    resize_img_pad,
)
from daras_ai_v2 import stable_diffusion
from daras_ai_v2.base import BasePage
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.image_segmentation import dis, u2net
from daras_ai_v2.repositioning import reposition_object, reposition_object_img_bytes
from daras_ai_v2.stable_diffusion import InpaintingModels


class ObjectInpaintingPage(BasePage):
    title = "An Object in Any Scene"
    slug = "ObjectInpainting"

    class RequestModel(BaseModel):
        input_image: str
        text_prompt: str

        num_outputs: int = 1
        quality: int = 50

        obj_scale: float = 0.30
        obj_pos_x: float = 0.4
        obj_pos_y: float = 0.45

        output_width: int = 512
        output_height: int = 512

        selected_model: str = InpaintingModels.jack_qiao.name

    class ResponseModel(BaseModel):
        resized_image: str
        obj_mask: str
        # diffusion_images: list[str]
        output_images: list[str]

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
                ### Object Photo
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
            st.error("Please provide a Prompt and a Object Photo", icon="⚠️")
            return False

        # upload input file if submitted
        if submitted:
            input_file = st.session_state.get("input_file")
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
                max_value=1024,
                step=128,
            )
        with col2:
            st.write("X")
        with col3:
            output_height = st.slider(
                "Height",
                key="output_height",
                min_value=512,
                max_value=1024,
                step=128,
            )

        st.write(
            """
            ### Object Repositioning Settings
            """
        )

        st.write("How _big_ should the object look?")
        col1, _ = st.columns(2)
        with col1:
            obj_scale = st.slider(
                "Scale",
                min_value=0.1,
                max_value=1.0,
                key="obj_scale",
            )

        st.write("_Where_ would you like to place the object in the scene?")
        col1, col2 = st.columns(2)
        with col1:
            pos_x = st.slider(
                "Position X",
                min_value=0.0,
                max_value=1.0,
                key="obj_pos_x",
            )
        with col2:
            pos_y = st.slider(
                "Position Y",
                min_value=0.0,
                max_value=1.0,
                key="obj_pos_y",
            )

        # show an example image
        img_cv2 = cv2.imread("static/obj.png")
        mask_cv2 = cv2.imread("static/obj_mask.png")

        # extract obj
        img, mask = reposition_object(
            orig_img=img_cv2,
            orig_mask=mask_cv2,
            out_size=(output_width, output_height),
            out_obj_scale=obj_scale,
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
                st.image(input_image_or_file, caption="Object Photo")
            else:
                st.empty()

        with col2:
            if output_images:
                for url in output_images:
                    st.image(url, caption=f"“{text_prompt}”")
            else:
                st.empty()

        with st.expander("Steps"):
            col1, col2, col3 = st.columns(3)

            with col1:
                if input_image_or_file:
                    st.image(input_image_or_file, caption="Input Image")
                else:
                    st.empty()

            with col2:
                resized_image = st.session_state.get("resized_image")
                if resized_image:
                    st.image(resized_image, caption="Repositioned Object")
                else:
                    st.empty()

                obj_mask = st.session_state.get("obj_mask")
                if obj_mask:
                    st.image(obj_mask, caption="Object Mask")
                else:
                    st.empty()

            with col3:
                diffusion_images = st.session_state.get("output_images")
                if diffusion_images:
                    for url in diffusion_images:
                        st.image(url, caption=f"Stable Diffusion - “{text_prompt}”")
                else:
                    st.empty()

    def run(self, state: dict):
        request: ObjectInpaintingPage.RequestModel = self.RequestModel.parse_obj(state)

        yield "Running Image Segmentation..."

        img_bytes = requests.get(request.input_image).content

        padded_img_bytes = resize_img_pad(
            img_bytes,
            (request.output_width, request.output_height),
        )
        padded_img_url = upload_file_from_bytes("padded_img.png", padded_img_bytes)

        obj_mask_bytes = dis(padded_img_url)

        yield "Repositioning..."

        re_img_bytes, re_mask_bytes = reposition_object_img_bytes(
            img_bytes=padded_img_bytes,
            mask_bytes=obj_mask_bytes,
            out_size=(request.output_width, request.output_height),
            out_obj_scale=request.obj_scale,
            out_pos_x=request.obj_pos_x,
            out_pos_y=request.obj_pos_y,
        )

        state["resized_image"] = upload_file_from_bytes("re_img.png", re_img_bytes)
        state["obj_mask"] = upload_file_from_bytes("obj_mask.png", re_mask_bytes)

        yield f"Generating Image..."

        diffusion_images = stable_diffusion.inpainting(
            selected_model=request.selected_model,
            prompt=request.text_prompt,
            num_outputs=request.num_outputs,
            edit_image=state["resized_image"],
            edit_image_bytes=re_img_bytes,
            mask=state["obj_mask"],
            mask_bytes=obj_mask_bytes,
            num_inference_steps=request.quality,
            width=request.output_width,
            height=request.output_height,
        )
        state["output_images"] = diffusion_images

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


if __name__ == "__main__":
    ObjectInpaintingPage().render()
