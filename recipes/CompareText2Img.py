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
    Text2ImgModels,
    text2img,
    instruct_pix2pix,
    sd_upscale,
    Schedulers,
    LoraWeight,
)
from daras_ai_v2.variables_widget import render_prompt_vars


class CompareText2ImgPage(BasePage):
    title = "Compare AI Image Generators"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/d127484e-88d9-11ee-b549-02420a000167/Compare%20AI%20Image%20generators.png.png"
    workflow = Workflow.COMPARE_TEXT2IMG
    slug_versions = [
        "CompareText2Img",
        "text2img",
        "compare-ai-image-generators",
    ]

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
        negative_prompt: str | None = None

        output_width: int | None = None
        output_height: int | None = None

        num_outputs: int | None = None
        quality: int | None = None
        dall_e_3_quality: str | None = None
        dall_e_3_style: str | None = None

        guidance_scale: float | None = None
        seed: int | None = None
        sd_2_upscaling: bool | None = None

        selected_models: (
            list[typing.Literal[tuple(e.name for e in Text2ImgModels)]] | None
        ) = None
        scheduler: typing.Literal[tuple(e.name for e in Schedulers)] | None = None

        edit_instruction: str | None = None
        image_guidance_scale: float | None = None

        loras: list[LoraWeight] | None = None

    class ResponseModel(BaseModel):
        output_images: dict[
            typing.Literal[tuple(e.name for e in Text2ImgModels)],
            list[FieldHttpUrl],
        ]

    @classmethod
    def get_example_preferred_fields(cls, state: dict) -> list[str]:
        return ["selected_models"]

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
        selected_models = enum_multiselect(
            Text2ImgModels,
            key="selected_models",
        )
        if selected_models and set(selected_models) <= {Text2ImgModels.flux_1_dev.name}:
            loras_input()
        else:
            gui.session_state.pop("loras", None)

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

        request.text_prompt = render_prompt_vars(request.text_prompt, gui.session_state)

        if not self.request.user.disable_safety_checker:
            yield "Running safety checker..."
            safety_checker(text=request.text_prompt)

        state["output_images"] = output_images = {}

        for selected_model in request.selected_models:
            model = Text2ImgModels[selected_model]
            yield f"Running {model.value}..."

            output_images[selected_model] = yield from text2img(
                model=model,
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
                loras=request.loras,
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

    def render_run_preview_output(self, state: dict):
        col1, col2 = gui.columns(2)
        with col1:
            gui.markdown("```properties\n" + state.get("text_prompt", "") + "\n```")
        with col2:
            self._render_outputs(state)

    def _render_outputs(self, state):
        selected_models = state.get("selected_models") or []
        for key in selected_models:
            output_images: dict = state.get("output_images", {}).get(key, [])
            for img in output_images:
                gui.image(
                    img, caption=Text2ImgModels[key].value, show_download_button=True
                )

    def get_raw_price(self, state: dict) -> int:
        selected_models = state.get("selected_models", [])
        total = 0
        for name in selected_models:
            match name:
                case Text2ImgModels.deepfloyd_if.name:
                    total += 5
                case Text2ImgModels.dall_e.name | Text2ImgModels.dall_e_3.name:
                    total += 15
                case _:
                    total += 2
        num_outputs = state.get("num_outputs") or 0
        return total * num_outputs


def loras_input(key: str = "loras"):
    lora_urls = gui.file_uploader(
        "**🔌 LoRAs**",
        help=(
            "The LoRAs to use for the image generation. "
            "You can use any number of LoRAs and they will be merged together to generate the final image.\n\n"
            "You can use [fal.ai](https://fal.ai/models/fal-ai/flux-lora-fast-training) to train your own LoRAs. "
        ),
        optional=True,
        accept_multiple_files=True,
        value=[lora["path"] for lora in gui.session_state.get(key) or []],
    )
    if lora_urls:
        gui.session_state[key] = [
            LoraWeight(path=url, scale=1).dict() for url in lora_urls
        ]
    else:
        gui.session_state.pop("loras", None)
