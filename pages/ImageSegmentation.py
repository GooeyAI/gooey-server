import json
import typing
from pathlib import Path

import cv2
import numpy as np
import requests
import streamlit as st
from furl import furl
from pydantic import BaseModel
from streamlit.components.v1 import html

from daras_ai.image_input import (
    upload_file_hq,
    upload_file_from_bytes,
    cv2_img_to_bytes,
    bytes_to_cv2_img,
)
from daras_ai_v2 import settings
from daras_ai_v2.base import BasePage
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.image_segmentation import u2net, ImageSegmentationModels, dis


class ImageSegmentationPage(BasePage):
    title = "Cutout an object from any image"
    slug = "ImageSegmentation"
    version = 2

    class RequestModel(BaseModel):
        input_image: str

        selected_model: typing.Literal[
            tuple(e.name for e in ImageSegmentationModels)
        ] | None
        mask_threshold: float | None

    class ResponseModel(BaseModel):
        output_image: str
        cutout_image: str

    def render_form(self) -> bool:
        with st.form("my_form"):
            st.write(
                """
                ### Input Photo
                Give us a photo of anything
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

    def render_settings(self):
        enum_selector(ImageSegmentationModels, "Model", key="selected_model")

        st.write(
            """
            ##### Edge Threshold
            Helps to remove edge artifacts. `0` will turn this off. `0.9` will aggressively cut down edges. 
            """
        )
        st.slider(
            min_value=0.0,
            max_value=1.0,
            label="Threshold",
            label_visibility="collapsed",
            key="mask_threshold",
        )

    def run_as_api_tab(self):
        super().run_as_api_tab()
        cutout_images = []
        input_files = st.file_uploader("input_files", accept_multiple_files=True)
        container = st.container()

        if not input_files:
            return

        for input_file in input_files:
            with st.spinner(f"Processing {input_file.name}..."):
                input_image = upload_file_hq(input_file)
                response = requests.post(
                    str(furl(settings.API_BASE_URL) / self.endpoint),
                    json={
                        "input_image": input_image,
                        "selected_model": "dis",
                        "mask_threshold": 0.8,
                    },
                )
            response.raise_for_status()

            col1, col2, col3 = st.columns(3)

            with col1:
                st.image(input_image, width=100)
            with col2:
                cutout_image = response.json()["cutout_image"]
                cutout_images.append(cutout_image)
                st.image(cutout_image, width=100)
            with col3:
                html(
                    """
                   <script src="https://cdnjs.cloudflare.com/ajax/libs/downloadjs/1.4.8/download.min.js"></script>
                    <button onClick='download("%s")' class="btn">
                        ⬇️ Download
                    </button>
                    <style>
                       .btn {
                       padding:8px;
                            display: inline-flex;
                            -webkit-box-align: center;
                            align-items: center;
                            -webkit-box-pack: center;
                            justify-content: center;
                            font-weight: 400;
                            padding: 0.25rem 0.75rem;
                            border-radius: 0.25rem;
                            margin: 0px;
                            line-height: 1.6;
                            color: white;
                            user-select: none;
                            background-color: rgb(8, 8, 8);
                            border: 1px solid rgba(255, 255, 255, 0.2);
                        }
                    </style>
                    """
                    % cutout_image
                )
        with container:
            html(
                """
                   <script src="https://cdnjs.cloudflare.com/ajax/libs/downloadjs/1.4.8/download.min.js"></script>
                    <button onClick='%s.map((e)=>download(e))' class="btn">
                        ⬇️ Download all
                    </button>
                    <style>
                       .btn {
                       padding:8px;
                            display: inline-flex;
                            -webkit-box-align: center;
                            align-items: center;
                            -webkit-box-pack: center;
                            justify-content: center;
                            font-weight: 400;
                            padding: 0.25rem 0.75rem;
                            border-radius: 0.25rem;
                            margin: 0px;
                            line-height: 1.6;
                            color: white;
                            user-select: none;
                            background-color: rgb(8, 8, 8);
                            border: 1px solid rgba(255, 255, 255, 0.2);
                        }
                    </style>
                
                """%json.dumps(cutout_images)
            )


    def run(self, state: dict) -> typing.Iterator[str | None]:

        request: ImageSegmentationPage.RequestModel = self.RequestModel.parse_obj(state)

        match request.selected_model:
            case ImageSegmentationModels.u2net.name:
                mask_bytes = u2net(request.input_image)
            case _:
                mask_bytes = dis(request.input_image)

        img_cv2 = bytes_to_cv2_img(requests.get(request.input_image).content)
        mask_cv2 = bytes_to_cv2_img(mask_bytes)

        threshold_value = int(255 * request.mask_threshold)
        mask_cv2[mask_cv2 < threshold_value] = 0

        kernel = np.ones((5, 5), np.float32) / 10
        mask_cv2 = cv2.filter2D(mask_cv2, -1, kernel)

        cutout_cv2 = 255 - mask_cv2
        img_cv2[mask_cv2 == 0] = 0

        cutout_cv2 = cv2.add(cutout_cv2, img_cv2)

        yield

        state["output_image"] = upload_file_from_bytes(
            f"gooey.ai Segmentation Mask - {Path(request.input_image).stem}.png",
            cv2_img_to_bytes(mask_cv2),
        )

        yield

        state["cutout_image"] = upload_file_from_bytes(
            f"gooey.ai Cutout - {Path(request.input_image).stem}.png",
            cv2_img_to_bytes(cutout_cv2),
        )

    def render_output(self):
        self.render_example(st.session_state)

        with st.expander("Steps"):
            col1, col2, col3 = st.columns(3)

            with col1:
                input_image = st.session_state.get("input_image")
                if input_image:
                    st.image(input_image, caption="Input Photo")
                else:
                    st.empty()

            with col2:
                output_image = st.session_state.get("output_image")
                if output_image:
                    st.image(output_image, caption=f"Segmentation Mask")
                else:
                    st.empty()

            with col3:
                cutout_image = st.session_state.get("cutout_image")
                if cutout_image:
                    st.image(cutout_image, caption=f"Cutout Image")
                else:
                    st.empty()

    def render_example(self, state: dict):
        col1, col2 = st.columns(2)

        with col1:
            input_image = state.get("input_image")
            if input_image:
                st.image(input_image, caption="Input Photo")
            else:
                st.empty()

        with col2:
            cutout_image = state.get("cutout_image")
            if cutout_image:
                st.image(cutout_image, caption=f"Cutout Image")
            else:
                st.empty()


if __name__ == "__main__":
    ImageSegmentationPage().render()
