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
)
from daras_ai_v2.stable_diffusion import Text2ImgModels, text2img


class CompareText2ImgPage(BasePage):
    title = "Compare AI Image Generators"
    slug_versions = [
        "CompareText2Img",
        "compare-ai-image-generators",
    ]

    sane_defaults = {
        "guidance_scale": 10,
        "seed": 42,
        "sd_2_upscaling": False,
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

    class ResponseModel(BaseModel):
        output_images: dict[
            typing.Literal[tuple(e.name for e in Text2ImgModels)], list[str]
        ]

    def render_form_v2(self):
        st.text_area(
            """
            ### Prompt
            Describe the scene that you'd like to generate. 
            """,
            key="text_prompt",
            placeholder="Iron man",
        )

    def validate_form_v2(self):
        assert st.session_state["text_prompt"], "Please provide a Prompt"
        assert st.session_state["selected_models"], "Please Select at least one model"

    def render_description(self):
        st.write(
            """
                This recipe takes any text and renders an image using multiple Text2Image engines. 
                
                Use it to understand which render e.g. DallE or Stable Diffusion is best for your particular prompt. 
            """
        )

    def render_settings(self):
        selected_model = enum_multiselect(
            Text2ImgModels,
            label="#### Selected Models",
            key="selected_models",
        )

        num_outputs_setting(selected_model)
        st.checkbox("**4x Upscaling (SD v2 only)**", key="sd_2_upscaling")
        negative_prompt_setting(selected_model)
        output_resolution_setting()

        col1, col2 = st.columns(2)
        with col1:
            guidance_scale_setting(selected_model)

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
                sd_2_upscaling=request.sd_2_upscaling,
                negative_prompt=request.negative_prompt,
            )

    def render_example(self, state: dict):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("```" + state.get("text_prompt", "").replace("\n", "") + "```")
        with col2:
            self._render_outputs(state)

    def _render_outputs(self, state):
        selected_models = state.get("selected_models", [])
        for key in selected_models:
            output_images: dict = state.get("output_images", {}).get(key, [])
            for img in output_images:
                st.image(img, caption=Text2ImgModels[key].value)

    # def preview_image(self, state: dict) -> str:
    #     # TODO: Which model to pick and if key will be available
    #     return state.get("output_images", [""])[0]
    def preview_description(self, state: dict) -> str:
        return "Create multiple AI photos from Stable Diffusion (1.5 -> 2.1) and DallE from one prompt. Determine which AI image generator from OpenAI, Stability.AI works best for your text."


if __name__ == "__main__":
    CompareText2ImgPage().render()
