import streamlit as st

from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.stable_diffusion import Text2ImgModels, InpaintingModels, Img2ImgModels


def img_model_settings(models_enum):
    st.write("### Image Generation Settings")
    selected_model = enum_selector(
        models_enum,
        label="#### Model",
        key="selected_model",
    )

    negative_prompt_setting(selected_model)

    num_outputs_setting(selected_model)
    if models_enum is not Img2ImgModels:
        output_resolution_setting()

    if models_enum is Text2ImgModels:
        sd_2_upscaling_setting()

    col1, col2 = st.columns(2)

    with col1:
        guidance_scale_setting(selected_model)

    with col2:
        if models_enum is Img2ImgModels:
            prompt_strength_setting(selected_model)
        if selected_model == Img2ImgModels.instruct_pix2pix.name:
            instruct_pix2pix_settings()

    return selected_model


def num_outputs_setting(selected_model: str = None):
    col1, col2 = st.columns(2, gap="medium")
    with col1:
        st.slider(
            label="##### Number of Outputs",
            key="num_outputs",
            min_value=1,
            max_value=4,
            step=1,
        )
    with col2:
        if selected_model != InpaintingModels.dall_e.name:
            st.slider(
                label="##### Quality",
                key="quality",
                min_value=10,
                max_value=200,
                step=10,
            )
        else:
            st.empty()


def output_resolution_setting():
    col1, col2, col3 = st.columns([10, 1, 10])
    with col1:
        st.slider(
            "##### Width",
            key="output_width",
            min_value=512,
            max_value=1152,
            step=64,
        )
    with col2:
        st.write("X")
    with col3:
        st.slider(
            "##### Height",
            key="output_height",
            min_value=512,
            max_value=1152,
            step=64,
        )
    st.write(
        """
        *Note: Dall-E only supports 512x512*
        """
    )


def sd_2_upscaling_setting():
    st.checkbox("**4x Upscaling**", key="sd_2_upscaling")
    st.caption("Note: Currently, only square images can be upscaled")


def guidance_scale_setting(selected_model: str = None):
    if selected_model not in [
        Text2ImgModels.dall_e.name,
        Text2ImgModels.jack_qiao,
    ]:
        st.number_input(
            label="""
##### 🎨️ Artistic Pressure
([*Text Guidance Scale*](https://getimg.ai/guides/interactive-guide-to-stable-diffusion-guidance-scale-parameter)) \\
How pressurized should the AI feel to produce what you want? \\
At lower values the image will effectively be random.
Values that are too high can also distort the image.
            """,
            key="guidance_scale",
            min_value=0.0,
            max_value=25.0,
            step=0.5,
        )


def instruct_pix2pix_settings():
    st.slider(
        label="""
##### 🌠️ Image Strength
([*Image Guidance Scale*](https://github.com/timothybrooks/instruct-pix2pix#tips)) \\
A higher value encourages to generate images that are closely linked to the source image, 
usually at the expense of lower image quality
""",
        key="image_guidance_scale",
        min_value=1.0,
        max_value=2.0,
        step=0.10,
    )


def prompt_strength_setting(selected_model: str = None):
    if selected_model in [
        Img2ImgModels.dall_e.name,
        Img2ImgModels.instruct_pix2pix.name,
    ]:
        return

    st.slider(
        label="""
        ##### Extent of Modification 
        (*Prompt Strength*)

        How much should the original image be modified?

        `0` will keep the original image intact.\\
        `0.9` will ignore the original image completely. 
        """,
        key="prompt_strength",
        min_value=0.0,
        max_value=0.9,
        step=0.05,
    )


def negative_prompt_setting(selected_model: str = None):
    if selected_model in [Text2ImgModels.dall_e.name, InpaintingModels.runway_ml.name]:
        return

    st.text_area(
        """
        ##### 🧽 Negative Prompt
        This allows you to specify what you DON'T want to see. 
        Useful negative prompts can be found [here](https://www.youtube.com/watch?v=cWZsizoAwT4).
        """,
        key="negative_prompt",
    )
