import math

import gooey_ui as st

from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.stable_diffusion import (
    Text2ImgModels,
    InpaintingModels,
    Img2ImgModels,
    ControlNetModels,
)


def img_model_settings(models_enum, render_model_selector=True):
    st.write("### Image Generation Settings")
    if render_model_selector:
        selected_model = model_selector(models_enum)
    else:
        selected_model = st.session_state.get("selected_model")

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
        if models_enum is Img2ImgModels and not st.session_state.get(
            "selected_controlnet_model"
        ):
            prompt_strength_setting(selected_model)
        if selected_model == Img2ImgModels.instruct_pix2pix.name:
            instruct_pix2pix_settings()

    return selected_model


def model_selector(models_enum):
    col1, col2 = st.columns(2)
    with col1:
        selected_model = enum_selector(
            models_enum,
            label="#### Model",
            key="selected_model",
            use_selectbox=True,
            allow_none=True,
        )
    with col2:
        if models_enum is Img2ImgModels:
            if st.session_state.get("selected_model") is None or st.session_state.get(
                "selected_model"
            ) in [
                Img2ImgModels.instruct_pix2pix.name,
                Img2ImgModels.dall_e.name,
                Img2ImgModels.jack_qiao.name,
                Img2ImgModels.sd_2.name,
            ]:
                st.session_state["selected_controlnet_model"] = None
            else:
                enum_selector(
                    ControlNetModels,
                    label="""
#### Control Net
Choose any [conditioning model](https://huggingface.co/lllyasviel?search=controlnet).
                    """,
                    key="selected_controlnet_model",
                    allow_none=True,
                    use_selectbox=True,
                )
    return selected_model


def num_outputs_setting(selected_model: str = None):
    col1, col2 = st.columns(2, gap="medium")
    with col1:
        st.slider(
            label="""
            ##### Number of Outputs
            Change the number of outputs for a single run here:
            """,
            key="num_outputs",
            min_value=1,
            max_value=4,
            step=1,
        )
        st.caption(
            """
            By default, each run produces one output per Model.
            """
        )
    with col2:
        if selected_model != InpaintingModels.dall_e.name:
            st.slider(
                label="""
                ##### Quality
                How precise, or focused do you want your output to be? 
                """,
                key="quality",
                min_value=10,
                max_value=200,
                step=10,
            )
            st.caption(
                """
                An increase in output quality is comparable to a gradual progression in any drawing process that begins with a draft version and ends with a finished product. 
                """
            )
        else:
            st.div()


RESOLUTIONS = {
    512: {
        (512, 512): "square",
        (576, 448): "A4",
        (640, 384): "laptop",
        (768, 320): "smartphone",
        (960, 256): "cinema",
        (1024, 256): "panorama",
    },
    768: {
        (768, 768): "square",
        (896, 640): "A4",
        (1024, 576): "laptop",
        (1024, 512): "smartphone",
        (1152, 512): "cinema",
        (1536, 384): "panorama",
    },
    1024: {
        (1024, 1024): "square",
        (1024, 768): "A4",
        (1280, 768): "laptop",
        (1536, 512): "smartphone",
        (1792, 512): "cinema",
        (2048, 512): "panorama",
    },
}

LANDSCAPE = "Landscape"
PORTRAIT = "Portrait"


def output_resolution_setting():
    col1, col2, col3 = st.columns(3)

    if "__pixels" not in st.session_state:
        saved = (
            st.session_state.get("output_width"),
            st.session_state.get("output_height"),
        )
        if not saved[0]:
            saved = (768, 768)
        if saved[0] < saved[1]:
            orientation = PORTRAIT
            saved = saved[::-1]
        else:
            orientation = LANDSCAPE
        for pixels, spec in RESOLUTIONS.items():
            for res in spec.keys():
                if res != saved:
                    continue
                st.session_state["__pixels"] = pixels
                st.session_state["__res"] = res
                st.session_state["__orientation"] = orientation
                break

    selected_model = st.session_state.get(
        "selected_model", st.session_state.get("selected_models", "")
    )
    if "jack_qiao" in selected_model or "sd_1_4" in selected_model:
        pixel_options = [512]
    elif "deepfloyd_if" in selected_model:
        pixel_options = [1024]
    else:
        pixel_options = [768, 1024]

    with col1:
        pixels = st.selectbox(
            "##### Size",
            key="__pixels",
            format_func=lambda x: f"{x}p",
            options=pixel_options,
        )
    with col2:
        res = st.selectbox(
            "##### Resolution",
            key="__res",
            format_func=lambda x: f"{x[0]} x {x[1]} ({RESOLUTIONS[pixels][x]})",
            options=RESOLUTIONS[pixels].keys(),
        )
    if res[0] != res[1]:
        with col3:
            orientation = st.selectbox(
                "##### Orientation",
                key="__orientation",
                options=[LANDSCAPE, PORTRAIT],
            )
        if orientation == PORTRAIT:
            res = res[::-1]

    st.session_state["output_width"] = res[0]
    st.session_state["output_height"] = res[1]


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
            How pressurized should the AI feel to produce what you want?
            How much creative freedom do you want the AI to have when interpreting your prompt?
            """,
            key="guidance_scale",
            min_value=0.0,
            max_value=25.0,
            step=0.5,
        )
        st.caption(
            """
            At lower values the image will effectively be random. The standard value is between 6-8. Values that are too high can also distort the image.
            """
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
        This allows you to specify what you DON'T want to see in your output.
        Useful negative prompts can be found [here](https://www.youtube.com/watch?v=cWZsizoAwT4).
        """,
        key="negative_prompt",
    )
    st.caption(
        """
        Text2Image engines can often generate disproportionate body parts, extra limbs or fingers, strange textures etc. Use negative prompting to avoid disfiguration or for creative outputs like avoiding certain colour schemes, elements or styles.
    """
    )
