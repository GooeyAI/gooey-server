import typing

import requests
import streamlit as st
from pydantic import BaseModel

from daras_ai.image_input import (
    upload_file_hq,
    upload_file_from_bytes,
    resize_img_pad,
)
from daras_ai_v2.base import BasePage
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.stable_diffusion import InpaintingModels, Img2ImgModels, img2img


class Img2ImgPage(BasePage):
    title = "Edit Any Image Using Text"
    slug = "Img2Img"

    class RequestModel(BaseModel):
        input_image: str
        text_prompt: str | None

        num_outputs: int | None
        quality: int | None
        prompt_strength: float | None

        output_width: int | None
        output_height: int | None

        selected_model: typing.Literal[tuple(e.name for e in Img2ImgModels)] | None

    class ResponseModel(BaseModel):
        resized_image: str
        output_images: list[str]

    def render_form(self) -> bool:
        with st.form("my_form"):
            if st.session_state["selected_model"] != InpaintingModels.dall_e.name:
                st.write(
                    """
                    ### Prompt
                    Describe your edits 
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
                ### Input Photo
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

        input_file = st.session_state.get("input_file")
        input_image = st.session_state.get("input_image")
        input_image_or_file = input_file or input_image

        # form validation
        if submitted and not input_image_or_file:
            st.error("Please provide an Input Image", icon="⚠️")
            return False

        # upload input file if submitted
        if submitted:
            input_file = st.session_state.get("input_file")
            if input_file:
                st.session_state["input_image"] = upload_file_hq(input_file)

        return submitted

    def render_description(self):
        st.write(
            """
                This recipe takes an image and a prompt and then attempts to alter the image, based on the text.

                Adjust the Prompt Strength in Settings to change how strongly the text should influence the image. 
            """
        )

    def render_settings(self):
        selected_model = enum_selector(
            Img2ImgModels,
            label="Image Model",
            key="selected_model",
        )

        st.slider(
            label="Prompt Strength",
            key="prompt_strength",
            min_value=0.0,
            max_value=1.0,
            help="How strongly should the prompt alter the image?",
        )

        col1, col2 = st.columns(2, gap="medium")
        with col1:
            st.slider(
                label="Number of Outputs",
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
            *Maximum size is 896x768 or 768x896 because of memory limits*
            """
        )
        col1, col2, col3 = st.columns([10, 1, 10])
        with col1:
            st.slider(
                "Width",
                key="output_width",
                min_value=512,
                max_value=1024,
                step=128,
            )
        with col2:
            st.write("X")
        with col3:
            st.slider(
                "Height",
                key="output_height",
                min_value=512,
                max_value=1024,
                step=128,
            )

    def render_output(self):
        text_prompt = st.session_state.get("text_prompt", "")
        input_file = st.session_state.get("input_file")
        input_image = st.session_state.get("input_image")
        input_image_or_file = input_image
        output_images = st.session_state.get("output_images")

        col1, col2 = st.columns(2)

        with col1:
            if input_image_or_file:
                st.image(input_image_or_file, caption="Input Image")
            else:
                st.empty()

        with col2:
            if output_images:
                for url in output_images:
                    st.image(url, caption=f"“{text_prompt}”")
            else:
                st.empty()

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

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request = self.RequestModel.parse_obj(state)

        img_bytes = requests.get(request.input_image).content

        yield "Resizing Image..."

        init_image_bytes = resize_img_pad(
            img_bytes, (request.output_width, request.output_height)
        )
        init_image = upload_file_from_bytes("resized_image.png", init_image_bytes)
        state["resized_image"] = init_image

        yield "Generating Image..."

        state["output_images"] = img2img(
            selected_model=request.selected_model,
            prompt=request.text_prompt,
            num_outputs=request.num_outputs,
            init_image=init_image,
            init_image_bytes=init_image_bytes,
            num_inference_steps=request.quality,
            prompt_strength=request.prompt_strength,
            width=request.output_width,
            height=request.output_height,
        )


if __name__ == "__main__":
    Img2ImgPage().render()
