import typing

from pydantic import BaseModel, Field

import gooey_gui as gui
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.enum_selector_widget import enum_multiselect
from daras_ai_v2.pydantic_validation import OptionalHttpUrlStr, HttpUrlStr
from daras_ai_v2.safety_checker import safety_checker
from daras_ai_v2.stable_diffusion import SD_IMG_MAX_SIZE
from daras_ai_v2.upscaler_models import UpscalerModels, run_upscaler_model


class CompareUpscalerPage(BasePage):
    title = "Compare AI Image Upscalers"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/64393e0c-88db-11ee-b428-02420a000168/AI%20Image%20Upscaler.png.png"
    workflow = Workflow.COMPARE_UPSCALER
    slug_versions = ["compare-ai-upscalers"]

    class RequestModel(BasePage.RequestModel):
        input_image: OptionalHttpUrlStr = Field(None, description="Input Image")
        input_video: OptionalHttpUrlStr = Field(None, description="Input Video")

        scale: int = Field(
            description="The final upsampling scale of the image", ge=1, le=4
        )

        selected_models: (
            list[typing.Literal[tuple(e.name for e in UpscalerModels)]] | None
        ) = None
        selected_bg_model: (
            typing.Literal[tuple(e.name for e in UpscalerModels if e.is_bg_model)]
            | None
        ) = None

    class ResponseModel(BaseModel):
        output_images: dict[
            typing.Literal[tuple(e.name for e in UpscalerModels)], HttpUrlStr
        ] = Field({}, description="Output Images")
        output_videos: dict[
            typing.Literal[tuple(e.name for e in UpscalerModels)], HttpUrlStr
        ] = Field({}, description="Output Videos")

    def validate_form_v2(self):
        assert gui.session_state.get("selected_models"), (
            "Please select at least one model"
        )

        assert gui.session_state.get("input_image") or gui.session_state.get(
            "input_video"
        ), "Please provide an Input Image or Video"

    def run_v2(
        self,
        request: "CompareUpscalerPage.RequestModel",
        response: "CompareUpscalerPage.ResponseModel",
    ) -> typing.Iterator[str | None]:
        if not self.request.user.disable_safety_checker and request.input_image:
            yield "Running safety checker..."
            safety_checker(image=request.input_image)

        response.output_images = {}
        response.output_videos = {}

        for selected_model in request.selected_models:
            model = UpscalerModels[selected_model]
            yield f"Running {model.label}..."
            if request.input_image:
                response.output_images[selected_model] = run_upscaler_model(
                    selected_model=model,
                    image=request.input_image,
                    scale=request.scale,
                )
            elif request.input_video:
                response.output_videos[selected_model] = run_upscaler_model(
                    selected_model=model,
                    video=request.input_video,
                    scale=request.scale,
                )

    def render_form_v2(self):
        selected_input_type = gui.horizontal_radio(
            "",
            options=["Image", "Video"],
            value="Video" if gui.session_state.get("input_video") else "Image",
        )
        if selected_input_type == "Video":
            gui.session_state.pop("input_image", None)
            gui.file_uploader(
                """
                #### Input Video
                """,
                key="input_video",
            )
        else:
            gui.session_state.pop("input_video", None)
            gui.file_uploader(
                """
                #### Input Image
                """,
                key="input_image",
                upload_meta=dict(resize=f"{SD_IMG_MAX_SIZE[0] * SD_IMG_MAX_SIZE[1]}@>"),
            )

        if selected_input_type == "Video":
            col1, col2 = gui.columns(2)
            with col1:
                gui.multiselect(
                    label="##### Upscaler Models",
                    options=[e.name for e in UpscalerModels if e.supports_video],
                    format_func=lambda x: UpscalerModels[x].label,
                    key="selected_models",
                )
            with col2:
                gui.selectbox(
                    label="##### Background Upscaler",
                    options=[e.name for e in UpscalerModels if e.is_bg_model],
                    format_func=lambda x: (
                        UpscalerModels[x].label if x else gui.BLANK_OPTION
                    ),
                    allow_none=True,
                    key="selected_bg_model",
                )
        else:
            enum_multiselect(
                UpscalerModels,
                label="#### 🤗 Compare Upscalers",
                key="selected_models",
            )

        gui.slider(
            """
            ### Scale
            Factor to scale image by
            """,
            key="scale",
            min_value=1,
            max_value=4,
            step=1,
        )

    def render_description(self):
        gui.write(
            """
            Have an old photo or just a funky AI picture? Run this workflow to compare the top image upscalers.
            """
        )

    def render_output(self):
        _render_outputs(gui.session_state)

    def render_run_preview_output(self, state: dict):
        col1, col2 = gui.columns(2)
        with col1:
            gui.image(state.get("input_image"), caption="Input Image")
        with col2:
            _render_outputs(state)

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


def _render_outputs(state):
    for key in state.get("selected_models") or []:
        img = (state.get("output_images") or {}).get(key)
        if img:
            gui.image(img, caption=UpscalerModels[key].label, show_download_button=True)

        vid = (state.get("output_videos") or {}).get(key)
        if vid:
            gui.video(vid, caption=UpscalerModels[key].label, show_download_button=True)
