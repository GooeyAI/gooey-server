import typing

import streamlit as st
from pydantic import BaseModel

from daras_ai_v2.base import BasePage
from daras_ai_v2.enum_selector_widget import enum_multiselect
from daras_ai_v2.img_model_settings_widgets import (
    negative_prompt_setting,
    guidance_scale_setting,
    num_outputs_setting,
    output_resolution_setting,
    instruct_pix2pix_settings,
    sd_2_upscaling_setting,
)
from daras_ai_v2.stable_diffusion import (
    Text2ImgModels,
    text2img,
    instruct_pix2pix,
    sd_upscale,
)


class CompareText2ImgPage(BasePage):
    title = "Compare AI Image Generators"
    slug_versions = [
        "CompareText2Img",
        "compare-ai-image-generators",
    ]

    sane_defaults = {
        "guidance_scale": 7.5,
        "seed": 42,
        "sd_2_upscaling": False,
        "image_guidance_scale": 1.2,
    }

    class RequestModel(BaseModel):
        text_prompt: str
        negative_prompt: str | None

        output_width: int | None
        output_height: int | None

        num_outputs: int | None
        quality: int | None

        guidance_scale: float | None
        seed: int | None
        sd_2_upscaling: bool | None

        selected_models: list[
            typing.Literal[tuple(e.name for e in Text2ImgModels)]
        ] | None

        edit_instruction: str | None
        image_guidance_scale: float | None

    class ResponseModel(BaseModel):
        output_images: dict[
            typing.Literal[tuple(e.name for e in Text2ImgModels)], list[str]
        ]

    def related_workflows(self) -> list:
        from recipes.FaceInpainting import FaceInpaintingPage
        from recipes.ObjectInpainting import ObjectInpaintingPage
        from recipes.GoogleImageGen import GoogleImageGenPage
        from recipes.TextToSpeech import TextToSpeechPage

        return [
            FaceInpaintingPage,
            ObjectInpaintingPage,
            GoogleImageGenPage,
            TextToSpeechPage,
        ]

    def render_form_v2(self):
        st.text_area(
            """
            ### 👩‍💻 Prompt
            Describe the scene that you'd like to generate. 
            """,
            key="text_prompt",
            placeholder="Iron man",
        )
        st.write("#### 🧨 Compare Image Models")
        st.caption(
            "Each selected model costs 2 credits to run except for Dall-E which is 15 credits per rendered image."
        )
        enum_multiselect(
            Text2ImgModels,
            key="selected_models",
        )

    def validate_form_v2(self):
        assert st.session_state["text_prompt"], "Please provide a prompt"
        assert st.session_state["selected_models"], "Please select at least one model"

    def render_description(self):
        st.write(
            """
            This recipe takes any text and renders an image using multiple Text2Image engines. 
            
            Use it to understand which image generator e.g. DallE or Stable Diffusion is best for your particular prompt. 
            """
        )

    def render_settings(self):
        if st.checkbox("📝 Edit Instructions"):
            st.text_area(
                """
                Describe how you want to change the generated image using [InstructPix2Pix](https://www.timothybrooks.com/instruct-pix2pix).
                """,
                key="__edit_instruction",
                placeholder="Give it sunglasses and a mustache",
            )
        st.session_state["edit_instruction"] = st.session_state.get(
            "__edit_instruction"
        )

        negative_prompt_setting()
        num_outputs_setting()
        output_resolution_setting()
        sd_2_upscaling_setting()
        col1, col2 = st.columns(2)
        with col1:
            guidance_scale_setting()
        with col2:
            if st.session_state.get("edit_instruction"):
                instruct_pix2pix_settings()

    def render_output(self):
        self._render_outputs(st.session_state)

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: CompareText2ImgPage.RequestModel = self.RequestModel.parse_obj(state)

        state["output_images"] = output_images = {}

        for selected_model in request.selected_models:
            yield f"Running {Text2ImgModels[selected_model].value}..."

            output_images[selected_model] = text2img(
                selected_model=selected_model,
                prompt=request.text_prompt,
                num_outputs=request.num_outputs,
                num_inference_steps=request.quality,
                width=request.output_width,
                height=request.output_height,
                guidance_scale=request.guidance_scale,
                seed=request.seed,
                negative_prompt=request.negative_prompt,
            )

            if request.edit_instruction:
                yield f"Running InstructPix2Pix..."

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
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("```properties\n" + state.get("text_prompt", "") + "\n```")
        with col2:
            self._render_outputs(state)

    def _render_outputs(self, state):
        selected_models = state.get("selected_models", [])
        for key in selected_models:
            output_images: dict = state.get("output_images", {}).get(key, [])
            for img in output_images:
                st.image(img, caption=Text2ImgModels[key].value)

    def preview_description(self, state: dict) -> str:
        return "Create multiple AI photos from Stable Diffusion (1.5 -> 2.1, Open/Midjourney) DallE from one prompt. Determine which AI image generator from OpenAI, Stability.AI works best for your text."

    def get_price(self) -> int:
        selected_models = st.session_state.get("selected_models", [])
        total = 0
        for name in selected_models:
            match name:
                case Text2ImgModels.dall_e.name:
                    total += 15
                case _:
                    total += 2
        return total


if __name__ == "__main__":
    CompareText2ImgPage().render()
