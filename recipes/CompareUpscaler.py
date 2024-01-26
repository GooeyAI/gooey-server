import typing

from pydantic import BaseModel

import gooey_ui as st
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.enum_selector_widget import enum_multiselect
from daras_ai_v2.face_restoration import UpscalerModels, run_upscaler_model
from daras_ai_v2.stable_diffusion import SD_IMG_MAX_SIZE
from daras_ai_v2.safety_checker import safety_checker

DEFAULT_COMPARE_UPSCALER_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/2e8ee512-93fe-11ee-a083-02420a0001c8/Image%20upscaler.jpg.png"


class CompareUpscalerPage(BasePage):
    title = "Compare AI Image Upscalers"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/64393e0c-88db-11ee-b428-02420a000168/AI%20Image%20Upscaler.png.png"
    workflow = Workflow.COMPARE_UPSCALER
    slug_versions = ["compare-ai-upscalers"]

    class RequestModel(BaseModel):
        input_image: str

        scale: int

        selected_models: (
            list[typing.Literal[tuple(e.name for e in UpscalerModels)]] | None
        )

    class ResponseModel(BaseModel):
        output_images: dict[typing.Literal[tuple(e.name for e in UpscalerModels)], str]

    def render_form_v2(self):
        st.file_uploader(
            """
            ### Input Image
            """,
            key="input_image",
            upload_meta=dict(resize=f"{SD_IMG_MAX_SIZE[0] * SD_IMG_MAX_SIZE[1]}@>"),
        )

        enum_multiselect(
            UpscalerModels,
            label="#### 🤗 Compare Upscalers",
            key="selected_models",
        )

    def validate_form_v2(self):
        assert st.session_state["selected_models"], "Please select at least one model"

        input_image = st.session_state.get("input_image")
        assert input_image, "Please provide an Input Image"

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

    def preview_image(self, state: dict) -> str | None:
        return DEFAULT_COMPARE_UPSCALER_META_IMG

    def render_description(self):
        st.write(
            """
            Have an old photo or just a funky AI picture? Run this workflow to compare the top image upscalers.
            """
        )

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: CompareUpscalerPage.RequestModel = self.RequestModel.parse_obj(state)

        if not self.request.user.disable_safety_checker:
            yield "Running safety checker..."
            safety_checker(image=request.input_image)

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
            self.render_buttons(img)

    def get_raw_price(self, state: dict) -> int:
        selected_models = state.get("selected_models", [])
        return 5 * len(selected_models)

    def related_workflows(self) -> list:
        from recipes.CompareText2Img import CompareText2ImgPage
        from recipes.GoogleImageGen import GoogleImageGenPage
        from recipes.ImageSegmentation import ImageSegmentationPage
        from recipes.Img2Img import Img2ImgPage

        return [
            CompareText2ImgPage,
            GoogleImageGenPage,
            ImageSegmentationPage,
            Img2ImgPage,
        ]
