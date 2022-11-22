import typing

import cv2
import requests
import streamlit as st
from pydantic import BaseModel

from daras_ai.image_input import (
    upload_file_hq,
    resize_img_pad,
    upload_file_from_bytes,
    bytes_to_cv2_img,
    cv2_img_to_bytes,
)
from daras_ai_v2 import stable_diffusion
from daras_ai_v2.base import BasePage
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.extract_face import (
    extract_and_reposition_face_cv2,
)
from daras_ai_v2.image_segmentation import dis
from daras_ai_v2.img_tools import overlay_rule_of_3rds
from daras_ai_v2.repositioning import reposition_object
from daras_ai_v2.stable_diffusion import InpaintingModels


class ObjectFaceInpainting(BasePage):
    title = "An Object in Any Scene"
    slug = "ObjectFaceInpainting"

    class RequestModel(BaseModel):
        text_prompt: str
        input_face_image: str
        input_obj_image: str

        num_outputs: int | None
        quality: int | None

        obj_scale: float | None
        obj_pos_x: float | None
        obj_pos_y: float | None

        face_scale: float | None
        face_pos_x: float | None
        face_pos_y: float | None

        output_width: int | None
        output_height: int | None

        selected_model: typing.Literal[tuple(e.name for e in InpaintingModels)] | None

    class ResponseModel(BaseModel):
        resized_image: str
        obj_mask: str
        diffusion_images: list[str]
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
                Give us a photo of anything
                """
            )
            st.file_uploader(
                "input_object_file",
                label_visibility="collapsed",
                key="input_object_file",
            )
            st.caption(
                "By uploading an image, you agree to Gooey.AI's [Privacy Policy](https://dara.network/privacy)"
            )

            st.write(
                """
                ### Face Photo
                Give us a photo of yourself, or anyone else
                """
            )
            st.file_uploader(
                "input_face_file",
                label_visibility="collapsed",
                key="input_face_file",
            )
            st.caption(
                "By uploading an image, you agree to Gooey.AI's [Privacy Policy](https://dara.network/privacy)"
            )

            submitted = st.form_submit_button("🏃‍ Submit")

        text_prompt = st.session_state.get("text_prompt")
        input_face_file = st.session_state.get("input_face_file")
        input_object_file = st.session_state.get("input_object_file")
        # input_image = st.session_state.get("input_image")
        # input_image_or_file = input_file or input_image
        #
        # # form validation
        # if submitted and not (text_prompt and input_image_or_file):
        #     st.error("Please provide a Prompt and a Object Photo", icon="⚠️")
        #     return False
        #
        # upload input file if submitted
        if submitted:
            if input_face_file:
                st.session_state["input_face_image"] = upload_file_hq(input_face_file)

            if input_object_file:
                st.session_state["input_obj_image"] = upload_file_hq(input_object_file)

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
            face_pos_x = st.slider(
                "Position X",
                min_value=0.0,
                max_value=1.0,
                key="face_pos_x",
            )
        with col2:
            face_pos_y = st.slider(
                "Position Y",
                min_value=0.0,
                max_value=1.0,
                key="face_pos_y",
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
            obj_pos_x = st.slider(
                "Position X",
                min_value=0.0,
                max_value=1.0,
                key="obj_pos_x",
            )
        with col2:
            obj_pos_y = st.slider(
                "Position Y",
                min_value=0.0,
                max_value=1.0,
                key="obj_pos_y",
            )

        # show an example image
        obj_img_cv2 = cv2.imread("static/obj.png")
        obj_mask_cv2 = cv2.imread("static/obj_mask.png")

        # show an example image
        face_img_cv2 = cv2.imread("static/face.png")

        # extract face
        face_img_cv2, face_mask_cv2 = extract_and_reposition_face_cv2(
            orig_img=face_img_cv2,
            out_size=(output_width, output_height),
            out_face_scale=face_scale,
            out_pos_x=face_pos_x,
            out_pos_y=face_pos_y,
        )

        # extract obj
        obj_img_cv2, obj_mask_cv2 = reposition_object(
            orig_img=obj_img_cv2,
            orig_mask=obj_mask_cv2,
            out_size=(output_width, output_height),
            out_obj_scale=obj_scale,
            out_pos_x=obj_pos_x,
            out_pos_y=obj_pos_y,
        )

        obj_img_cv2[face_img_cv2 > 0] = 0
        obj_mask_cv2[face_mask_cv2 > 0] = 0

        img = obj_img_cv2 + face_img_cv2
        mask = obj_mask_cv2 + face_mask_cv2

        col1, col2 = st.columns(2)
        with col1:
            overlay_rule_of_3rds(img)
            st.image(img, width=300)
        with col2:
            overlay_rule_of_3rds(mask)
            st.image(mask, width=300)

    def render_output(self):
        text_prompt = st.session_state.get("text_prompt", "")
        input_obj_image = st.session_state.get("input_obj_image")
        input_face_image = st.session_state.get("input_face_image")
        output_images = st.session_state.get("output_images")

        col1, col2 = st.columns(2)

        with col1:
            if input_obj_image:
                st.image(input_obj_image, caption="Object Photo")
            else:
                st.empty()
            if input_face_image:
                st.image(input_face_image, caption="Face Photo")
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
                if input_obj_image:
                    st.image(input_obj_image, caption="Object Photo")
                else:
                    st.empty()
                if input_face_image:
                    st.image(input_face_image, caption="Face Photo")
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
                        st.image(url, caption=f"“{text_prompt}”")
                else:
                    st.empty()

    def run(self, state: dict) -> typing.Iterator[str | None]:
        yield "Uploading..."

        request: ObjectFaceInpainting.RequestModel = self.RequestModel.parse_obj(state)

        obj_img_bytes = requests.get(request.input_obj_image).content
        face_img_bytes = requests.get(request.input_face_image).content

        yield "Running Image Segmentation..."

        obj_img_bytes = resize_img_pad(
            obj_img_bytes,
            (request.output_width, request.output_height),
        )
        obj_img_url = upload_file_from_bytes("padded_img.png", obj_img_bytes)

        obj_mask_bytes = dis(obj_img_url)

        yield "Extracting Face..."

        # extract face
        face_img_cv2, face_mask_cv2 = extract_and_reposition_face_cv2(
            orig_img=bytes_to_cv2_img(face_img_bytes),
            out_size=(request.output_width, request.output_height),
            out_face_scale=request.face_scale,
            out_pos_x=request.face_pos_x,
            out_pos_y=request.face_pos_y,
        )

        # extract obj
        obj_img_cv2, obj_mask_cv2 = reposition_object(
            orig_img=bytes_to_cv2_img(obj_img_bytes),
            orig_mask=bytes_to_cv2_img(obj_mask_bytes),
            out_size=(request.output_width, request.output_height),
            out_obj_scale=request.obj_scale,
            out_pos_x=request.obj_pos_x,
            out_pos_y=request.obj_pos_y,
        )

        obj_img_cv2[face_img_cv2 > 0] = 0
        obj_mask_cv2[face_mask_cv2 > 0] = 0

        img = obj_img_cv2 + face_img_cv2
        mask = obj_mask_cv2 + face_mask_cv2

        re_img_bytes = cv2_img_to_bytes(img)
        state["resized_image"] = upload_file_from_bytes(
            "resized_image.png", re_img_bytes
        )
        re_mask_bytes = cv2_img_to_bytes(mask)
        state["obj_mask"] = upload_file_from_bytes("obj_mask.png", re_mask_bytes)

        yield f"Generating Image..."

        diffusion_images = stable_diffusion.inpainting(
            selected_model=request.selected_model,
            prompt=request.text_prompt,
            num_outputs=request.num_outputs,
            edit_image=state["resized_image"],
            edit_image_bytes=re_img_bytes,
            mask=state["obj_mask"],
            mask_bytes=re_mask_bytes,
            num_inference_steps=request.quality,
            width=request.output_width,
            height=request.output_height,
        )
        state["output_images"] = diffusion_images

        # yield "Running gfpgan..."
        #
        # output_images = map_parallel(gfpgan, diffusion_images)
        #
        # state["output_images"] = [
        #     upload_file_from_bytes(
        #         safe_filename(f"gooey.ai inpainting - {prompt.strip()}.png"),
        #         img_bytes,
        #         # requests.get(url).content,
        #     )
        #     for img_bytes in output_images
        # ]


if __name__ == "__main__":
    ObjectFaceInpainting().render()
