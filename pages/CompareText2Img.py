import typing

import streamlit as st
from pydantic import BaseModel

from daras_ai_v2.base import BasePage
from daras_ai_v2.enum_selector_widget import enum_multiselect
from daras_ai_v2.stable_diffusion import Text2ImgModels, text2img


class CompareText2ImgPage(BasePage):
    title = "Compare Image Generators"
    slug = "CompareText2Img"

    sane_defaults = {
        "guidance_scale": 10,
        "seed": 0,
        "sd_2_upscaling": False,
    }

    class RequestModel(BaseModel):
        text_prompt: str

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
        output_images: dict[typing.Literal[tuple(e.name for e in Text2ImgModels)], str]

    def render_form(self) -> bool:
        with st.form("my_form"):
            st.write(
                """
                ### Prompt
                Describe the scene that you'd like to generate. 
                """
            )
            st.text_area(
                "text_prompt",
                label_visibility="collapsed",
                key="text_prompt",
                placeholder="Iron man",
            )

            submitted = st.form_submit_button("🏃‍ Submit")

        text_prompt = st.session_state.get("text_prompt")
        if submitted and not text_prompt:
            st.error("Please provide a Prompt", icon="⚠️")
            return False

        selected_models = st.session_state.get("selected_models")
        if submitted and not selected_models:
            st.error("Please Select at least one model", icon="⚠️")
            return False

        return submitted

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
            label="Selected Models",
            key="selected_models",
        )

        col1, col2 = st.columns(2, gap="medium")
        with col1:
            st.slider(
                label="# of Outputs",
                key="num_outputs",
                min_value=1,
                max_value=4,
            )
        with col2:
            if selected_model != Text2ImgModels.dall_e.name:
                st.slider(
                    label="Quality",
                    key="quality",
                    min_value=10,
                    max_value=200,
                    step=10,
                )
            else:
                st.empty()

        st.write(
            """
            ### Output Resolution
            """
        )
        col1, col2, col3 = st.columns([10, 1, 10])
        with col1:
            st.slider(
                "Width",
                key="output_width",
                min_value=512,
                max_value=768,
                step=64,
            )
        with col2:
            st.write("X")
        with col3:
            st.slider(
                "Height",
                key="output_height",
                min_value=512,
                max_value=768,
                step=64,
            )

        st.write("#### Advanced settings")
        col1, col2 = st.columns(2)
        with col1:
            st.number_input("Guidance scale", key="guidance_scale", step=0.1)
        with col2:
            st.number_input("Seed", key="seed", step=1)
        st.checkbox("4x Upscaling (SD v2 only)", key="sd_2_upscaling")

    def render_output(self):
        output_images: dict = st.session_state.get("output_images")
        if output_images:
            for key, imgs in output_images.items():
                st.write(f"##### {Text2ImgModels[key].value}")
                for img in imgs:
                    st.image(img)
        else:
            st.empty()

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
            )

    def render_example(self, state: dict):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("```" + state.get("text_prompt", "").replace("\n", "") + "```")
        with col2:
            output_images: dict = state.get("output_images")
            if output_images:
                for key, imgs in output_images.items():
                    st.write(f"**{Text2ImgModels[key].value}**")
                    for img in imgs:
                        st.image(img)
            else:
                st.empty()


if __name__ == "__main__":
    CompareText2ImgPage().render()
