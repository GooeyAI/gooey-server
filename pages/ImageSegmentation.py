import typing
from pathlib import Path
import numpy as np
import requests
import streamlit as st
from pydantic import BaseModel

from daras_ai.image_input import (
    upload_file_hq,
    upload_file_from_bytes,
    cv2_img_to_bytes,
    bytes_to_cv2_img,
)
from daras_ai_v2.base import BasePage
from daras_ai_v2.image_segmentation import u2net, dis


class ImageSegmentationPage(BasePage):
    title = "Cutout an object from any image"
    slug = "ImageSegmentation"
    version = 2

    class RequestModel(BaseModel):
        input_image: str

    class ResponseModel(BaseModel):
        output_image: str
        cutout_image: str

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

        mask_bytes = dis(request.input_image)

        yield "Uploading..."

        state["output_image"] = upload_file_from_bytes(
            f"gooey.ai Segmentation Mask - {Path(request.input_image).stem}",
            mask_bytes,
        )

        img_cv2 = bytes_to_cv2_img(requests.get(request.input_image).content)
        mask_cv2 = bytes_to_cv2_img(mask_bytes)

        cutout_cv2 = np.ones(img_cv2.shape, dtype=np.uint8) * 255
        cutout_cv2[mask_cv2 > 0] = 0
        img_cv2[mask_cv2 == 0] = 0
        cutout_cv2 += img_cv2

        state["cutout_image"] = upload_file_from_bytes(
            f"gooey.ai Cutout - {Path(request.input_image).stem}",
            cv2_img_to_bytes(cutout_cv2),
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

        cutout_image = state.get("cutout_image")
        if cutout_image:
            st.image(cutout_image, caption=f"Cutout Image")
        else:
            st.empty()


if __name__ == "__main__":
    ImageSegmentationPage().render()
