import gooey_ui as st

from daras_ai_v2.enum_selector_widget import enum_selector, enum_multiselect
from daras_ai_v2.stable_diffusion import (
    Text2ImgModels,
    InpaintingModels,
    Img2ImgModels,
    ControlNetModels,
    controlnet_model_explanations,
    Schedulers,
)


def img_model_settings(
    models_enum,
    render_model_selector=True,
    show_scheduler=False,
    require_controlnet=False,
    extra_explanations: dict[ControlNetModels, str] = None,
    controlnet_explanation: str = "### 🎛️ Control Net\n[Control Net models](https://huggingface.co/lllyasviel?search=controlnet) provide a layer of refinement to the image generation process that blends the prompt with the control image. Choose your preferred models:",
    low_explanation: str = "At {low} the prompted visual will remain intact, regardless of the control nets",
    high_explanation: str = "At {high} the control nets will be applied tightly to the prompted visual, possibly overriding the prompt",
):
    st.write("#### Image Generation Settings")
    if render_model_selector:
        selected_model = model_selector(
            models_enum,
            require_controlnet=require_controlnet,
            extra_explanations=extra_explanations,
            controlnet_explanation=controlnet_explanation,
            low_explanation=low_explanation,
            high_explanation=high_explanation,
        )
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

    if show_scheduler:
        col1, col2 = st.columns(2)
        with col1:
            scheduler_setting(selected_model)

    return selected_model


def model_selector(
    models_enum,
    require_controlnet=False,
    extra_explanations: dict[ControlNetModels, str] = None,
    controlnet_explanation: str = "### 🎛️ Control Net\n[Control Net models](https://huggingface.co/lllyasviel?search=controlnet) provide a layer of refinement to the image generation process that blends the prompt with the control image. Choose your preferred models:",
    low_explanation: str = "At {low} the prompted visual will remain intact, regardless of the control nets",
    high_explanation: str = "At {high} the control nets will be applied tightly to the prompted visual, possibly overriding the prompt",
):
    controlnet_unsupported_models = [
        Img2ImgModels.instruct_pix2pix.name,
        Img2ImgModels.dall_e.name,
        Img2ImgModels.jack_qiao.name,
        Img2ImgModels.sd_2.name,
    ]
    col1, col2 = st.columns(2)
    with col1:
        selected_model = enum_selector(
            models_enum,
            label="""
            #### 🤖 Choose your preferred AI Model
            """,
            key="selected_model",
            use_selectbox=True,
            exclude=controlnet_unsupported_models if require_controlnet else [],
        )
        st.caption(
            """
            Search for our available models [here](https://huggingface.co/models?pipeline_tag=text-to-image) to learn more about them.
            Please use our default settings for optimal results if you're a beginner.   
            """
        )
        if (
            models_enum is Img2ImgModels
            and st.session_state.get("selected_model") in controlnet_unsupported_models
        ):
            if "selected_controlnet_model" in st.session_state:
                st.session_state["selected_controlnet_model"] = None
        elif models_enum is Img2ImgModels:
            enum_multiselect(
                ControlNetModels,
                label=controlnet_explanation,
                key="selected_controlnet_model",
                checkboxes=False,
                allow_none=not require_controlnet,
            )
            with col2:
                controlnet_settings(
                    extra_explanations=extra_explanations,
                    low_explanation=low_explanation,
                    high_explanation=high_explanation,
                )
    return selected_model


CONTROLNET_CONDITIONING_SCALE_RANGE: tuple[float, float] = (0.0, 2.0)


def controlnet_settings(
    extra_explanations: dict[ControlNetModels, str] = None,
    low_explanation: str = "At {low} the prompted visual will remain intact, regardless of the control nets",
    high_explanation: str = "At {high} the control nets will be applied tightly to the prompted visual, possibly overriding the prompt",
):
    models = st.session_state.get("selected_controlnet_model", [])
    if not models:
        return

    if extra_explanations is None:
        extra_explanations = {}
    explanations = controlnet_model_explanations | extra_explanations

    state_values = st.session_state.get("controlnet_conditioning_scale", [])
    new_values = []
    st.write(
        """
        ##### ⚖️ Conditioning Scales
        """,
        className="gui-input",
    )
    st.caption(
        f"""
        `{low_explanation.format(low=int(CONTROLNET_CONDITIONING_SCALE_RANGE[0]))}`.
        
        `{high_explanation.format(high=int(CONTROLNET_CONDITIONING_SCALE_RANGE[1]))}`. 
        """
    )
    for i, model in enumerate(sorted(models)):
        key = f"controlnet_conditioning_scale_{model}"
        try:
            st.session_state.setdefault(key, state_values[i])
        except IndexError:
            pass
        new_values.append(
            controlnet_weight_setting(
                selected_controlnet_model=model, explanations=explanations, key=key
            ),
        )
    st.session_state["controlnet_conditioning_scale"] = new_values


def controlnet_weight_setting(
    *,
    selected_controlnet_model: str,
    explanations: dict[ControlNetModels, str],
    key: str = "controlnet_conditioning_scale",
):
    model = ControlNetModels[selected_controlnet_model]
    return st.slider(
        label=f"""
        {explanations[model]}.
        """,
        key=key,
        min_value=CONTROLNET_CONDITIONING_SCALE_RANGE[0],
        max_value=CONTROLNET_CONDITIONING_SCALE_RANGE[1],
        step=0.05,
    )


def num_outputs_setting(selected_models: str | list[str] = None):
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
        quality_setting(selected_models)


def quality_setting(selected_models=None):
    if not isinstance(selected_models, list):
        selected_models = [selected_models]
    if any(
        [
            selected_model in [InpaintingModels.dall_e.name]
            for selected_model in selected_models
        ]
    ):
        return
    if any(
        [
            selected_model in [Text2ImgModels.dall_e_3.name]
            for selected_model in selected_models
        ]
    ):
        st.selectbox(
            """##### Dalle 3 Quality""",
            options=[
                "standard",
                "hd",
            ],
            key="dall_e_3_quality",
        )
        st.selectbox(
            """##### Dalle 3 Style""",
            options=[
                "natural",
                "vivid",
            ],
            key="dall_e_3_style",
        )
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


RESOLUTIONS: dict[int, dict[str, str]] = {
    256: {
        "256, 256": "square",
    },
    512: {
        "512, 512": "square",
        "576, 448": "A4",
        "640, 384": "laptop",
        "768, 320": "smartphone",
        "960, 256": "cinema",
        "1024, 256": "panorama",
    },
    768: {
        "768, 768": "square",
        "896, 640": "A4",
        "1024, 576": "laptop",
        "1024, 512": "smartphone",
        "1152, 512": "cinema",
        "1536, 384": "panorama",
    },
    1024: {
        "1024, 1024": "square",
        "1024, 768": "A4",
        "1280, 768": "laptop",
        "1536, 512": "smartphone",
        "1792, 512": "cinema",
        "2048, 512": "panorama",
        "1792, 1024": "wide",
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
                if res != f"{int(saved[0])}, {int(saved[1])}":
                    continue
                st.session_state["__pixels"] = pixels
                st.session_state["__res"] = res
                st.session_state["__orientation"] = orientation
                break

    selected_models = (
        st.session_state.get("selected_model", st.session_state.get("selected_models"))
        or ""
    )
    if not isinstance(selected_models, list):
        selected_models = [selected_models]

    allowed_shapes = None
    if "jack_qiao" in selected_models or "sd_1_4" in selected_models:
        pixel_options = [512]
    elif selected_models == ["deepfloyd_if"]:
        pixel_options = [1024]
    elif selected_models == ["dall_e"]:
        pixel_options = [256, 512, 1024]
        allowed_shapes = ["square"]
    elif selected_models == ["dall_e_3"]:
        pixel_options = [1024]
        allowed_shapes = ["square", "wide"]
    else:
        pixel_options = [512, 768]

    with col1:
        pixels = st.selectbox(
            "##### Size",
            key="__pixels",
            format_func=lambda x: f"{x}p",
            options=pixel_options,
        )
    with col2:
        res_options = [
            res
            for res, shape in RESOLUTIONS[pixels or pixel_options[0]].items()
            if not allowed_shapes or shape in allowed_shapes
        ]
        res = st.selectbox(
            "##### Resolution",
            key="__res",
            format_func=lambda r: f"{r.split(', ')[0]} x {r.split(', ')[1]} ({RESOLUTIONS[pixels][r]})",
            options=res_options,
        )
        res = tuple(map(int, res.split(", ")))

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


def scheduler_setting(selected_model: str = None):
    if selected_model in [
        Text2ImgModels.dall_e.name,
        Text2ImgModels.jack_qiao,
    ]:
        return
    enum_selector(
        Schedulers,
        label="""
        ##### Scheduler
        Schedulers or Samplers are algorithms that allow us to set an iterative process on your run. They are used across models to find the preferred balance between the generation speed and output quality. 

        We recommend using our default settings. Learn more, [here](https://huggingface.co/docs/diffusers/api/schedulers/overview).
        """,
        allow_none=True,
        use_selectbox=True,
        key="scheduler",
    )


def guidance_scale_setting(selected_model: str = None):
    if selected_model in [
        Text2ImgModels.dall_e.name,
        Text2ImgModels.jack_qiao,
    ]:
        return
    st.slider(
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
    if selected_model in [Text2ImgModels.dall_e.name]:
        return

    st.text_area(
        """
        ##### 🧽 Negative Prompt
        This allows you to specify what you DON'T want to see in your output.
        Useful negative prompts can be found [here](https://www.youtube.com/watch?v=cWZsizoAwT4).
        """,
        key="negative_prompt",
        placeholder="ugly, disfigured, low quality, blurry, nsfw",
    )
    st.caption(
        """
        Image generation engines can often generate disproportionate body parts, extra limbs or fingers, strange textures etc. Use negative prompting to avoid disfiguration or for creative outputs like avoiding certain colour schemes, elements or styles.
        """
    )
