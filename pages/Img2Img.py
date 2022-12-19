import typing

import requests
import streamlit as st
from pydantic import BaseModel

from daras_ai.image_input import (
    upload_file_hq,
)
from daras_ai_v2.base import BasePage
from daras_ai_v2.img_model_settings_widgets import img_model_settings
from daras_ai_v2.stable_diffusion import (
    InpaintingModels,
    Img2ImgModels,
    img2img,
    SD_MAX_SIZE,
)


class Img2ImgPage(BasePage):
    title = "Edit Any Image Using Text"
    slug_versions = ["Img2Img"]

    sane_defaults = {
        "num_outputs": 1,
        "quality": 50,
        "output_width": 512,
        "output_height": 512,
        "guidance_scale": 7.5,
        "prompt_strength": 0.4,
        "sd_2_upscaling": False,
    }

    class RequestModel(BaseModel):
        input_image: str
        text_prompt: str | None

        selected_model: typing.Literal[tuple(e.name for e in Img2ImgModels)] | None
        negative_prompt: str | None

        num_outputs: int | None
        quality: int | None

        output_width: int | None
        output_height: int | None

        guidance_scale: float | None
        prompt_strength: float | None

        sd_2_upscaling: bool | None

    class ResponseModel(BaseModel):
        output_images: list[str]

    def render_form(self) -> bool:
        with st.form("my_form"):
            if st.session_state["selected_model"] != InpaintingModels.dall_e.name:
                st.text_area(
                    """
                    ### Prompt
                    Describe your edits 
                    """,
                    key="text_prompt",
                    placeholder="Iron man",
                )

            st.file_uploader(
                """
                ### Input Photo
                """,
                key="input_file",
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
                st.session_state["input_image"] = upload_file_hq(
                    input_file, resize=SD_MAX_SIZE
                )

        return submitted

    def render_description(self):
        st.write(
            """
                This recipe takes an image and a prompt and then attempts to alter the image, based on the text.

                Adjust the Prompt Strength in Settings to change how strongly the text should influence the image. 
            """
        )

    def render_settings(self):
        img_model_settings(Img2ImgModels)

    def render_output(self):
        text_prompt = st.session_state.get("text_prompt", "")
        input_image = st.session_state.get("input_image")
        output_images = st.session_state.get("output_images", [])

        for url in output_images:
            st.image(url, caption=f"{text_prompt}")

        st.image(input_image, caption="Input Image")

    def render_example(self, state: dict):
        output_images = state.get("output_images", [])
        for img in output_images:
            st.image(img, caption=state.get("text_prompt", ""))

        input_image = state.get("input_image")
        st.image(input_image, caption="Input Image")

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request = self.RequestModel.parse_obj(state)

        init_image = request.input_image
        init_image_bytes = requests.get(init_image).content

        yield "Generating Image..."

        state["output_images"] = img2img(
            selected_model=request.selected_model,
            prompt=request.text_prompt,
            num_outputs=request.num_outputs,
            init_image=init_image,
            init_image_bytes=init_image_bytes,
            num_inference_steps=request.quality,
            prompt_strength=request.prompt_strength,
            negative_prompt=request.negative_prompt,
            guidance_scale=request.guidance_scale,
            sd_2_upscaling=request.sd_2_upscaling,
        )

    def preview_image(self, state: dict) -> str:
        return state.get("output_images", [""])[0]

    def preview_description(self, state: dict) -> str:
        return "This recipe takes an image and a prompt and then attempts to alter the image, based on the text."


if __name__ == "__main__":
    Img2ImgPage().render()
