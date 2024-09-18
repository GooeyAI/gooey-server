import typing

from daras_ai_v2.pydantic_validation import FieldHttpUrl
from pydantic import BaseModel

import gooey_gui as gui
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.descriptions import prompting101
from daras_ai_v2.enum_selector_widget import enum_multiselect
from daras_ai_v2.img_model_settings_widgets import (
    negative_prompt_setting,
    guidance_scale_setting,
    num_outputs_setting,
    output_resolution_setting,
    instruct_pix2pix_settings,
    sd_2_upscaling_setting,
    scheduler_setting,
)
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.safety_checker import safety_checker
from daras_ai_v2.stable_diffusion import (
    TextToImageModels,
    text2img,
    instruct_pix2pix,
    sd_upscale,
    Schedulers,
)

DEFAULT_COMPARE_TEXT2IMG_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/039110ba-1f72-11ef-8d23-02420a00015d/Compare%20image%20generators.jpg"


class CompareText2ImgPage(BasePage):
    title = "Compare AI Image Generators"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/d127484e-88d9-11ee-b549-02420a000167/Compare%20AI%20Image%20generators.png.png"
    workflow = Workflow.COMPARE_TEXT2IMG
    slug_versions = [
        "CompareText2Img",
        "text2img",
        "compare-ai-image-generators",
    ]
    sdk_method_name = "textToImage"

    sane_defaults = {
        "guidance_scale": 7.5,
        "seed": 42,
        "sd_2_upscaling": False,
        "image_guidance_scale": 1.2,
        "dall_e_3_quality": "standard",
        "dall_e_3_style": "vivid",
    }

    class RequestModel(BasePage.RequestModel):
        text_prompt: str
        negative_prompt: str | None

        output_width: int | None
        output_height: int | None

        num_outputs: int | None
        quality: int | None
        dall_e_3_quality: str | None
        dall_e_3_style: str | None

        guidance_scale: float | None
        seed: int | None
        sd_2_upscaling: bool | None

        selected_models: list[TextToImageModels.api_enum] | None
        scheduler: Schedulers.api_enum | None

        edit_instruction: str | None
        image_guidance_scale: float | None

    class ResponseModel(BaseModel):
        output_images: dict[TextToImageModels.api_enum, list[FieldHttpUrl]]

    @classmethod
    def get_example_preferred_fields(cls, state: dict) -> list[str]:
        return ["selected_models"]

    def preview_image(self, state: dict) -> str | None:
        return DEFAULT_COMPARE_TEXT2IMG_META_IMG

    def related_workflows(self) -> list:
        from recipes.FaceInpainting import FaceInpaintingPage
        from recipes.ObjectInpainting import ObjectInpaintingPage
        from recipes.GoogleImageGen import GoogleImageGenPage
        from recipes.QRCodeGenerator import QRCodeGeneratorPage

        return [
            FaceInpaintingPage,
            ObjectInpaintingPage,
            GoogleImageGenPage,
            QRCodeGeneratorPage,
        ]

    def render_form_v2(self):
        gui.text_area(
            """
            #### 👩‍💻 Prompt
            Describe the scene that you'd like to generate.
            """,
            key="text_prompt",
            placeholder="Iron man",
        )
        gui.caption(
            """
            Refer to the saved examples or our basic prompt guide in the ‘Details’ dropdown menu.
        """
        )
        gui.write("#### 🧨 Compare Image Models")
        gui.caption(
            "Each selected model costs 2 credits to run except for Dall-E which is 15 credits per rendered image."
        )
        gui.caption(
            """
        Confused about what each model looks like?
        [Check out our prompt guide](https://docs.google.com/presentation/d/1RaoMP0l7FnBZovDAR42zVmrUND9W5DW6eWet-pi6kiE/edit#slide=id.g210b1678eba_0_26).
        """
        )
        enum_multiselect(
            TextToImageModels,
            key="selected_models",
        )

    def validate_form_v2(self):
        assert gui.session_state["text_prompt"], "Please provide a prompt"
        assert gui.session_state["selected_models"], "Please select at least one model"

    def render_usage_guide(self):
        youtube_video("TxT-mTYP0II")

    def render_description(self):
        gui.markdown(
            """
            This recipe takes any text and renders an image using multiple Text2Image engines.
            Use it to understand which image generator e.g. DallE or Stable Diffusion is best for your particular prompt.
            """
        )
        prompting101()

    def render_settings(self):
        gui.write(
            """
            Customize the image output for your text prompt with these Settings. 
            """
        )
        gui.caption(
            """
            You can also enable ‘Edit Instructions’ to use InstructPix2Pix that allows you to change your generated image output with a follow-up written instruction.
            """
        )
        if gui.checkbox("📝 Edit Instructions"):
            gui.text_area(
                """
                Describe how you want to change the generated image using [InstructPix2Pix](https://www.timothybrooks.com/instruct-pix2pix).
                """,
                key="__edit_instruction",
                placeholder="Give it sunglasses and a mustache",
            )
        gui.session_state["edit_instruction"] = gui.session_state.get(
            "__edit_instruction"
        )

        negative_prompt_setting()
        output_resolution_setting()
        num_outputs_setting(gui.session_state.get("selected_models", []))
        sd_2_upscaling_setting()
        col1, col2 = gui.columns(2)
        with col1:
            guidance_scale_setting()
            scheduler_setting()
        with col2:
            if gui.session_state.get("edit_instruction"):
                instruct_pix2pix_settings()

    def render_output(self):
        self._render_outputs(gui.session_state)

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: CompareText2ImgPage.RequestModel = self.RequestModel.parse_obj(state)

        if not self.request.user.disable_safety_checker:
            yield "Running safety checker..."
            safety_checker(text=request.text_prompt)

        state["output_images"] = output_images = {}

        for selected_model in request.selected_models:
            yield f"Running {TextToImageModels[selected_model].label}..."

            output_images[selected_model] = text2img(
                selected_model=selected_model,
                prompt=request.text_prompt,
                num_outputs=request.num_outputs,
                num_inference_steps=request.quality,
                dall_e_3_quality=request.dall_e_3_quality,
                dall_e_3_style=request.dall_e_3_style,
                width=request.output_width,
                height=request.output_height,
                guidance_scale=request.guidance_scale,
                seed=request.seed,
                negative_prompt=request.negative_prompt,
                scheduler=request.scheduler,
            )

            if request.edit_instruction:
                yield "Running InstructPix2Pix..."

                output_images[selected_model] = instruct_pix2pix(
                    prompt=request.edit_instruction,
                    num_outputs=1,
                    num_inference_steps=request.quality,
                    negative_prompt=request.negative_prompt,
                    guidance_scale=request.guidance_scale,
                    seed=request.seed,
                    images=output_images[selected_model],
                    image_guidance_scale=request.image_guidance_scale,
                )

            if request.sd_2_upscaling:
                yield "Upscaling..."

                output_images[selected_model] = [
                    upscaled
                    for image in output_images[selected_model]
                    for upscaled in sd_upscale(
                        prompt=request.text_prompt,
                        num_outputs=1,
                        num_inference_steps=10,
                        negative_prompt=request.negative_prompt,
                        guidance_scale=request.guidance_scale,
                        seed=request.seed,
                        image=image,
                    )
                ]

    def render_example(self, state: dict):
        col1, col2 = gui.columns(2)
        with col1:
            gui.markdown("```properties\n" + state.get("text_prompt", "") + "\n```")
        with col2:
            self._render_outputs(state)

    def _render_outputs(self, state):
        selected_models = state.get("selected_models", [])
        for key in selected_models:
            output_images: dict = state.get("output_images", {}).get(key, [])
            for img in output_images:
                gui.image(
                    img, caption=TextToImageModels[key].label, show_download_button=True
                )

    def preview_description(self, state: dict) -> str:
        return "Create multiple AI photos from one prompt using Stable Diffusion (1.5 -> 2.1, Open/Midjourney), DallE, and other models.  Find out which AI Image generator works best for your text prompt on comparing OpenAI, Stability.AI etc."

    def get_raw_price(self, state: dict) -> int:
        selected_models = state.get("selected_models", [])
        total = 0
        for name in selected_models:
            match name:
                case TextToImageModels.deepfloyd_if.name:
                    total += 5
                case TextToImageModels.dall_e.name | TextToImageModels.dall_e_3.name:
                    total += 15
                case _:
                    total += 2
        num_outputs = state.get("num_outputs") or 0
        return total * num_outputs
