import gooey_gui as gui

from daras_ai_v2.enum_selector_widget import enum_multiselect, enum_selector
from daras_ai_v2.stable_diffusion import (
    ControlNetModels,
    Img2ImgModels,
    Schedulers,
    Text2ImgModels,
    controlnet_model_explanations,
)

# openai / google models that generally dont support controlnet, guidance scale, inference steps etc.
PROPRIETARY_MODELS = {
    Text2ImgModels.nano_banana_pro.name,
    Text2ImgModels.nano_banana.name,
    Text2ImgModels.gpt_image_1.name,
    Text2ImgModels.gpt_image_1_5.name,
    Text2ImgModels.dall_e_3.name,
    Text2ImgModels.dall_e.name,
}

# self hosted diffusion models that have full support for controlnet, guidance scale, inference steps etc.
SELF_HOSTED_SD_MODELS = {
    Text2ImgModels.dream_shaper.name,
    Text2ImgModels.dreamlike_2.name,
    Text2ImgModels.sd_2.name,
    Text2ImgModels.sd_1_5.name,
}


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
    gui.write("#### Image Generation Settings")
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
        selected_model = gui.session_state.get("selected_model")
    if selected_model:
        selected_models = {selected_model}
    else:
        selected_models = set()

    negative_prompt_setting(selected_models)

    num_outputs_setting(selected_models)
    if models_enum is not Img2ImgModels:
        output_resolution_setting(selected_models)

    if models_enum is Text2ImgModels:
        sd_2_upscaling_setting()

    col1, col2 = gui.columns(2)

    with col1:
        guidance_scale_setting(selected_models)

    with col2:
        if models_enum is Img2ImgModels and not gui.session_state.get(
            "selected_controlnet_model"
        ):
            prompt_strength_setting(selected_models)
        if Img2ImgModels.instruct_pix2pix.name in selected_models:
            instruct_pix2pix_settings()

    if show_scheduler:
        col1, col2 = gui.columns(2)
        with col1:
            scheduler_setting(selected_models)

    return selected_model


def model_selector(
    models_enum,
    require_controlnet=False,
    extra_explanations: dict[ControlNetModels, str] = None,
    controlnet_explanation: str = "### 🎛️ Control Net\n[Control Net models](https://huggingface.co/lllyasviel?search=controlnet) provide a layer of refinement to the image generation process that blends the prompt with the control image. Choose your preferred models:",
    low_explanation: str = "At {low} the prompted visual will remain intact, regardless of the control nets",
    high_explanation: str = "At {high} the control nets will be applied tightly to the prompted visual, possibly overriding the prompt",
):
    choices = models_enum
    if require_controlnet:
        choices = [model for model in choices if model.name in SELF_HOSTED_SD_MODELS]
    col1, col2 = gui.columns(2)
    with col1:
        selected_model = enum_selector(
            choices,
            label="#### 🤖 Choose your preferred AI Model",
            key="selected_model",
            use_selectbox=True,
        )
        gui.caption(
            """
            Search for our available models [here](https://huggingface.co/models?pipeline_tag=text-to-image) to learn more about them.
            Please use our default settings for optimal results if you're a beginner.   
            """
        )
        if models_enum is Img2ImgModels and selected_model in SELF_HOSTED_SD_MODELS:
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
        elif "selected_controlnet_model" in gui.session_state:
            gui.session_state["selected_controlnet_model"] = None
    return selected_model


CONTROLNET_CONDITIONING_SCALE_RANGE: tuple[float, float] = (0.0, 2.0)


def controlnet_settings(
    extra_explanations: dict[ControlNetModels, str] = None,
    low_explanation: str = "At {low} the prompted visual will remain intact, regardless of the control nets",
    high_explanation: str = "At {high} the control nets will be applied tightly to the prompted visual, possibly overriding the prompt",
):
    models = gui.session_state.get("selected_controlnet_model", [])
    if not models:
        return

    if extra_explanations is None:
        extra_explanations = {}
    explanations = controlnet_model_explanations | extra_explanations

    state_values = gui.session_state.get("controlnet_conditioning_scale", [])
    new_values = []
    gui.write(
        """
        ##### ⚖️ Conditioning Scales
        """,
        className="gui-input",
    )
    gui.caption(
        f"""
        `{low_explanation.format(low=int(CONTROLNET_CONDITIONING_SCALE_RANGE[0]))}`.
        
        `{high_explanation.format(high=int(CONTROLNET_CONDITIONING_SCALE_RANGE[1]))}`. 
        """
    )
    for i, model in enumerate(sorted(models)):
        key = f"controlnet_conditioning_scale_{model}"
        try:
            gui.session_state.setdefault(key, state_values[i])
        except IndexError:
            pass
        new_values.append(
            controlnet_weight_setting(
                selected_controlnet_model=model, explanations=explanations, key=key
            ),
        )
    gui.session_state["controlnet_conditioning_scale"] = new_values


def controlnet_weight_setting(
    *,
    selected_controlnet_model: str,
    explanations: dict[ControlNetModels, str],
    key: str = "controlnet_conditioning_scale",
):
    model = ControlNetModels[selected_controlnet_model]
    return gui.slider(
        label=f"""
        {explanations[model]}.
        """,
        key=key,
        min_value=CONTROLNET_CONDITIONING_SCALE_RANGE[0],
        max_value=CONTROLNET_CONDITIONING_SCALE_RANGE[1],
        step=0.05,
    )


def num_outputs_setting(selected_models: set[str]):
    col1, col2 = gui.columns(2, gap="medium")
    with col1:
        gui.slider(
            label="""
            ##### Number of Outputs
            Change the number of outputs for a single run here:
            """,
            key="num_outputs",
            min_value=1,
            max_value=4,
            step=1,
        )
        gui.caption(
            """
            By default, each run produces one output per Model.
            """
        )
    with col2:
        quality_setting(selected_models)


def quality_setting(selected_models: set[str]):
    if Text2ImgModels.dall_e_3.name in selected_models:
        gui.selectbox(
            """##### Dalle 3 Quality""",
            options=["standard", "hd"],
            key="dall_e_3_quality",
        )
        gui.selectbox(
            """##### Dalle 3 Style""",
            options=["natural", "vivid"],
            key="dall_e_3_style",
        )

    if selected_models & {
        Text2ImgModels.gpt_image_1.name,
        Text2ImgModels.gpt_image_1_5.name,
    }:
        gui.selectbox(
            """##### GPT Image 1 Quality""",
            options=["low", "medium", "high"],
            key="gpt_image_1_quality",
        )

    if selected_models & (
        SELF_HOSTED_SD_MODELS | {Img2ImgModels.instruct_pix2pix.name}
    ):
        gui.slider(
            label="""
            ##### Quality
            How precise, or focused do you want your output to be? 
            """,
            key="quality",
            min_value=10,
            max_value=200,
            step=10,
        )
        gui.caption(
            """
            An increase in output quality is comparable to a gradual progression in any drawing process that begins with a draft version and ends with a finished product. 
            """
        )


RESOLUTIONS: dict[str, dict[str, str]] = {
    "256p": {
        "256 x 256": "square",
    },
    "512p": {
        "512 x 512": "square",
        "576 x 448": "A4",
        "640 x 384": "laptop",
        "768 x 320": "smartphone",
        "960 x 256": "cinema",
        "1024 x 256": "panorama",
    },
    "768p": {
        "768 x 768": "square",
        "896 x 640": "A4",
        "1024 x 576": "laptop",
        "1024 x 512": "smartphone",
        "1152 x 512": "cinema",
        "1536 x 384": "panorama",
    },
    "1024p": {
        "1024 x 1024": "square",
        "1024 x 768": "A4",
        "1280 x 768": "laptop",
        "1536 x 512": "smartphone",
        "1792 x 512": "cinema",
        "2048 x 512": "panorama",
        "1792 x 1024": "wide",
        "1536 x 1024": "camera",
    },
    "1K": {
        "1920 x 1080": "16:9",
        "1620 x 1080": "3:2",
        "1440 x 1080": "4:3",
        "1350 x 1080": "5:4",
        "1080 x 1080": "1:1",
    },
    "2K": {
        "2560 x 1440": "16:9",
        "2160 x 1440": "3:2",
        "1920 x 1440": "4:3",
        "1800 x 1440": "5:4",
        "1440 x 1440": "1:1",
    },
    "4K": {
        "3840 x 2160": "16:9",
        "3240 x 2160": "3:2",
        "2880 x 2160": "4:3",
        "2700 x 2160": "5:4",
        "2160 x 2160": "1:1",
    },
}
LANDSCAPE = "Landscape"
PORTRAIT = "Portrait"

NANO_BANANA_RESOLUTIONS = ["1K", "2K", "4K"]


def output_resolution_setting(selected_models: set[str]):
    if "__pixels" not in gui.session_state:
        saved = (
            gui.session_state.get("output_width"),
            gui.session_state.get("output_height"),
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
                if res != f"{int(saved[0])} x {int(saved[1])}":
                    continue
                gui.session_state["__pixels"] = pixels
                gui.session_state["__res"] = res
                gui.session_state["__orientation"] = orientation
                break

    allowed_shapes = None
    if not selected_models:
        pixel_options = ["1K"]
    elif selected_models <= {
        Text2ImgModels.nano_banana.name,
        Text2ImgModels.nano_banana_pro.name,
    }:
        pixel_options = NANO_BANANA_RESOLUTIONS
    elif selected_models <= {Text2ImgModels.flux_1_dev.name}:
        pixel_options = ["1024p"]
    elif selected_models <= {Text2ImgModels.dall_e.name}:
        pixel_options = ["256p", "512p", "1024p"]
        allowed_shapes = ["square"]
    elif selected_models <= {Text2ImgModels.dall_e_3.name}:
        pixel_options = ["1024p"]
        allowed_shapes = ["square", "wide"]
    elif selected_models <= {Text2ImgModels.gpt_image_1.name}:
        pixel_options = ["1024p"]
        allowed_shapes = ["square", "camera"]
    else:
        pixel_options = ["512p", "768p"]

    col1, col2, col3 = gui.columns(3)
    with col1:
        pixels = gui.selectbox("##### Size", key="__pixels", options=pixel_options)
    with col2:
        res_options = [
            res
            for res, shape in RESOLUTIONS[pixels].items()
            if not allowed_shapes or shape in allowed_shapes
        ]
        res = gui.selectbox(
            "##### Resolution",
            key="__res",
            format_func=lambda r: f"{r} ({RESOLUTIONS[pixels][r]})",
            options=res_options,
        )
        res = tuple(map(int, res.split("x")))

    if res[0] != res[1]:
        with col3:
            orientation = gui.selectbox(
                "##### Orientation",
                key="__orientation",
                options=[LANDSCAPE, PORTRAIT],
            )
        if orientation == PORTRAIT:
            res = res[::-1]

    gui.session_state["output_width"] = res[0]
    gui.session_state["output_height"] = res[1]


def sd_2_upscaling_setting():
    gui.checkbox("**4x Upscaling**", key="sd_2_upscaling")
    gui.caption("Note: Currently, only square images can be upscaled")


def scheduler_setting(selected_models: set[str]):
    if not selected_models & SELF_HOSTED_SD_MODELS:
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


def guidance_scale_setting(selected_models: set[str]):
    if selected_models & PROPRIETARY_MODELS:
        return
    # Flux Pro Kontext requires guidance_scale >= 1.0
    if Img2ImgModels.flux_pro_kontext.name in selected_models:
        min_value = 1.0
    else:
        min_value = 0.0
    gui.slider(
        label="""
        ##### 🎨️ Artistic Pressure
        ([*Text Guidance Scale*](https://getimg.ai/guides/interactive-guide-to-stable-diffusion-guidance-scale-parameter)) \\
        How pressurized should the AI feel to produce what you want?
        How much creative freedom do you want the AI to have when interpreting your prompt?
        """,
        key="guidance_scale",
        min_value=min_value,
        max_value=25.0,
        step=0.5,
    )
    gui.caption(
        """
            At lower values the image will effectively be random. The standard value is between 6-8. Values that are too high can also distort the image.
            """
    )


def instruct_pix2pix_settings():
    gui.slider(
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


def prompt_strength_setting(selected_models: set[str]):
    if not selected_models & SELF_HOSTED_SD_MODELS:
        return

    gui.slider(
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


def negative_prompt_setting(selected_models: set[str]):
    if not selected_models & (
        SELF_HOSTED_SD_MODELS | {Img2ImgModels.instruct_pix2pix.name}
    ):
        return

    gui.text_area(
        """
        ##### 🧽 Negative Prompt
        This allows you to specify what you DON'T want to see in your output.
        Useful negative prompts can be found [here](https://www.youtube.com/watch?v=cWZsizoAwT4).
        """,
        key="negative_prompt",
        placeholder="ugly, disfigured, low quality, blurry, nsfw",
    )
    gui.caption(
        """
        Image generation engines can often generate disproportionate body parts, extra limbs or fingers, strange textures etc. Use negative prompting to avoid disfiguration or for creative outputs like avoiding certain colour schemes, elements or styles.
        """
    )
