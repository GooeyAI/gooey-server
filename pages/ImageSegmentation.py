import typing
from pathlib import Path

import streamlit as st
from pydantic import BaseModel

from daras_ai.image_input import upload_file_hq, upload_file_from_bytes
from daras_ai_v2.base import BasePage
from daras_ai_v2.image_segmentation import u2net


class ImageSegmentationPage(BasePage):
    title = "Image Segmentation"
    slug = "ImageSegmentation"
    version = 2

    class RequestModel(BaseModel):
        input_image: str

    class ResponseModel(BaseModel):
        output_image: str

    def render_form(self) -> bool:
        with st.form("my_form"):
            st.write(
                """
                ### Input Photo
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

        input_file = st.session_state.get("input_file")
        input_image = st.session_state.get("input_image")
        input_image_or_file = input_file or input_image

        # form validation
        if submitted and not input_image_or_file:
            st.error("Please provide an Input Photo", icon="⚠️")
            return False

        # upload input file if submitted
        if submitted:
            input_file = st.session_state.get("input_file")
            if input_file:
                st.session_state["input_image"] = upload_file_hq(input_file)

        return submitted

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request = self.RequestModel.parse_obj(state)

        img_bytes = u2net(request.input_image)

        yield "Uploading..."

        state["output_image"] = upload_file_from_bytes(
            f"gooey.ai Segmentation Mask - {Path(request.input_image).stem}",
            img_bytes,
        )

    def render_output(self):
        self.render_example(st.session_state)

    def render_example(self, state: dict):
        input_image = state.get("input_image")
        input_file = state.get("input_file")
        input_image_or_file = input_image or input_file
        output_image = state.get("output_image")

        col1, col2 = st.columns(2)

        with col1:
            if input_image_or_file:
                st.image(input_image_or_file, caption="Input Photo")
            else:
                st.empty()

        with col2:
            if output_image:
                st.image(output_image, caption=f"Segmentation Mask")
            else:
                st.empty()


if __name__ == "__main__":
    ImageSegmentationPage().render()
