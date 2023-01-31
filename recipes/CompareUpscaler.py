import typing

import streamlit as st
from pydantic import BaseModel

from daras_ai.image_input import upload_file_hq
from daras_ai_v2.base import BasePage
from daras_ai_v2.enum_selector_widget import enum_multiselect
from daras_ai_v2.face_restoration import UpscalerModels, run_upscaler_model
from daras_ai_v2.stable_diffusion import IMG_MAX_SIZE


class CompareUpscalerPage(BasePage):
    title = "Compare AI Image Upscalers"
    slug_versions = ["compare-ai-upscalers"]

    class RequestModel(BaseModel):
        input_image: str

        scale: int

        selected_models: list[
            typing.Literal[tuple(e.name for e in UpscalerModels)]
        ] | None

    class ResponseModel(BaseModel):
        output_images: dict[typing.Literal[tuple(e.name for e in UpscalerModels)], str]

    def render_form_v2(self):
        st.file_uploader(
            """
            ### Input Image
            """,
            key="input_file",
            upload_key="input_image",
        )

        enum_multiselect(
            UpscalerModels,
            label="#### 🤗 Selected Models",
            key="selected_models",
        )

    def validate_form_v2(self):
        assert st.session_state["selected_models"], "Please select at least one model"

        input_file = st.session_state.get("input_file")
        input_image = st.session_state.get("input_image")
        input_image_or_file = input_file or input_image
        assert input_image_or_file, "Please provide an Input Image"

        # upload input file
        if input_file:
            st.session_state["input_image"] = upload_file_hq(
                input_file, resize=IMG_MAX_SIZE
            )

    def render_settings(self):
        st.slider(
            """
            ### Scale
            Factor to scale image by
            """,
            key="scale",
            min_value=1,
            max_value=4,
            step=1,
        )

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: CompareUpscalerPage.RequestModel = self.RequestModel.parse_obj(state)

        state["output_images"] = output_images = {}

        for selected_model in request.selected_models:
            yield f"Running {UpscalerModels[selected_model].value}..."
            output_images[selected_model] = run_upscaler_model(
                selected_model=selected_model,
                image=request.input_image,
                scale=request.scale,
            )

    def render_output(self):
        self._render_outputs(st.session_state)

    def render_example(self, state: dict):
        col1, col2 = st.columns(2)
        with col1:
            st.image(state.get("input_image"), caption="Input Image")
        with col2:
            self._render_outputs(state)

    def _render_outputs(self, state):
        selected_models = state.get("selected_models", [])
        for key in selected_models:
            img: dict = state.get("output_images", {}).get(key)
            if not img:
                continue
            st.image(img, caption=UpscalerModels[key].value)

    def get_price(self) -> int:
        selected_models = st.session_state.get("selected_models", [])
        total = 5 * len(selected_models)
        return total
