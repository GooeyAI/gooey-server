import typing

from furl import furl
from pydantic import BaseModel

import gooey_ui as st
from daras_ai_v2 import settings
from daras_ai_v2.base import BasePage
from daras_ai_v2.img_model_settings_widgets import (
    guidance_scale_setting,
    model_selector,
    controlnet_settings,
)
from daras_ai_v2.stable_diffusion import (
    Text2ImgModels,
    controlnet,
    ControlNetModels,
    controlnet_model_explanations,
    text2img,
)

controlnet_qr_model_explanations = {
    ControlNetModels.sd_controlnet_tile: "preserve small details mainly in the qr code which makes it more readable",
    ControlNetModels.sd_controlnet_brightness: "make the qr code darker and background lighter (contrast helps qr readers)",
}
controlnet_model_explanations.update(controlnet_qr_model_explanations)


class QRCodeGeneratorPage(BasePage):
    title = "Create AI Art QR Codes...FAST"
    slug_versions = [
        "art-qr-code",
        "qr",
        "qr-code",
    ]

    sane_defaults = {
        "scheduler": "EulerAncestralDiscreteScheduler",
        "selected_model": Text2ImgModels.dream_shaper.name,
        "selected_controlnet_model": [
            ControlNetModels.sd_controlnet_tile.name,
            ControlNetModels.sd_controlnet_brightness.name,
        ],
        "size": 512,
        "num_images": 5,
        "num_inference_steps": 100,
        "guidance_scale": 9,
        "controlnet_conditioning_scale_sd_controlnet_tile": 0.25,
        "controlnet_conditioning_scale_sd_controlnet_brightness": 0.45,
        "seed": 1331,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__.update(self.sane_defaults)

    class RequestModel(BaseModel):
        image: str

        text_prompt: str | None
        negative_prompt: str | None

        selected_model: typing.Literal[tuple(e.name for e in Text2ImgModels)] | None
        selected_controlnet_model: typing.Literal[
            tuple(e.name for e in ControlNetModels)
        ]

        width: int | None
        height: int | None

        guidance_scale: float | None
        controlnet_conditioning_scale: typing.List[float]

        num_images: int | None
        num_inference_steps: int | None
        scheduler: str | None

        seed: int | None

    class ResponseModel(BaseModel):
        output_images: dict[
            typing.Literal[tuple(e.name for e in Text2ImgModels)], list[str]
        ]

    def related_workflows(self) -> list:
        from recipes.CompareText2Img import CompareText2ImgPage
        from recipes.Img2Img import Img2ImgPage
        from recipes.FaceInpainting import FaceInpaintingPage
        from recipes.EmailFaceInpainting import EmailFaceInpaintingPage

        return [
            CompareText2ImgPage,
            Img2ImgPage,
            FaceInpaintingPage,
            EmailFaceInpaintingPage,
        ]

    def render_form_v2(self):
        st.text_area(
            """
            ### 🔗 URL
            Enter your URL, link or text. Generally shorter is better. URLs are automatically shortened.
            """,
            key="qr_code_input_text",
            placeholder="https://www.gooey.ai",
        )
        # st.file_uploader(
        #     """
        #     -- OR -- Upload an existing qr code. It will be reformatted and cleaned.
        #     """,
        #     key="qr_code_input_image",
        #     accept=["image/*"],
        # )
        st.text_area(
            """
            ### 👩‍💻 Prompt
            Describe the subject/scene of the qr code. Some prompts blend better with qr codes than others.
            """,
            key="text_prompt",
            placeholder="Bright sunshine coming through the cracks of a wet, cave wall of big rocks",
        )
        # st.file_uploader(
        #     """
        #     -- OPTIONAL -- Upload an initial image to blend the qr code into. This can help the AI understand what your prompt means instead of generating everything from scratch.
        #     """,
        #     key="initial_image_input",
        #     accept=["image/*"],
        # )

    def validate_form_v2(self):
        assert st.session_state["text_prompt"], "Please provide a prompt"
        assert (
            st.session_state["qr_code_input_text"]
            or st.session_state["qr_code_input_image"]
        ), "Please provide either a qr code image or text"

    def render_description(self):
        st.markdown(
            """
            Enter your URL (or text) and an image prompt and we'll generate an arty QR code with your artistic style and content in about 30 seconds. This is a rad way to advertise your website in IRL or print on a poster.
            It is made possible by the open source [Control Net](https://github.com/lllyasviel/ControlNet).

            #### Prompting 101: 

            ###### Step 1: Create an idea or visualization in your mind. 
            `I want an image of an astronaut in a space suit walking on the streets of Mumbai.`
            """
        )
        st.markdown(
            """
            ###### Step 2: Think about your descriptors and break it down as follows: 

            - What is the Medium of this image? \\
            eg. It is a painting, a sculpture, an old photograph, portrait, 3D render, etc.\n
            - What/Who are the Subject(s) or Main Object(s) in the image? \\
            eg. A human, an animal, an identity like gender, race, or occupation like dancer, astronaut etc. \n
            - What is the Style? \\
            eg. Is it Analogue photography, a watercolor, a line drawing, digital painting etc. \n
            - What are the Details? \\
            eg. facial features or expressions, the space and landscape, lighting or the colours etc. 
            """
        )
        st.markdown(
            f"""
            ###### Step 3: Construct your prompt:
            `An analogue film still of an astronaut in a space suit walking on the busy streets of Mumbai, golden light on the astronaut, 4k`
            [example]({furl(settings.APP_BASE_URL).add(path='compare-ai-image-generators').add({"example_id": "s9nmzy34"}).url})
            """
        )
        st.markdown(
            """
            You can keep editing your prompt until you have your desired output. Consider AI generators as a collaborative tool. 
            ##### What is the difference between Submit and Regenerate? 
            Each AI generation has a unique Seed number. A random seed is created when you initiate the first run on clicking the Submit button. The seed is maintained as you continue editing the image with different setting options on each subsequent Submit click.\n
            However, by clicking the Regenerate button, the AI will generate a new Seed and a completely new/different set of outputs.
            """
        )

    def render_settings(self):
        st.write(
            """
            Customize the qr code output for your text prompt with these Settings. 
            """
        )
        st.text_area(
            """
            ##### 🧽 Negative Prompt
            List keywords that you DON'T want to see in your qr code.
            """,
            key="negative_prompt",
            placeholder="ugly, disfigured, low quality, blurry, nsfw",
        )
        col1, col2 = st.columns(2)
        with col1:
            st.caption(
                """
            ### 🤖 Generative Model
            Choose the model responsible for generating the content around the qr code.
            """
            )
            model_selector(
                Text2ImgModels,
                same_line=False,
            )
        with col2:
            guidance_scale_setting()
            controlnet_settings(controlnet_model_explanations)

    def render_output(self):
        state = st.session_state
        self._render_outputs(state)

    def _render_outputs(self, state: dict):
        selected_models = state.get("selected_models", [])
        for key in selected_models:
            output_images: dict = state.get("output_images", {}).get(key, [])
            for img in output_images:
                st.image(img, caption=Text2ImgModels[key].value)

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: QRCodeGeneratorPage.RequestModel = self.RequestModel.parse_obj(state)

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

    def render_example(self, state: dict):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("```properties\n" + state.get("text_prompt", "") + "\n```")
        with col2:
            self._render_outputs(state)

    def preview_description(self, state: dict) -> str:
        return "Enter your URL (or text) and an image prompt and we'll generate an arty QR code with your artistic style and content in about 30 seconds. This is a rad way to advertise your website in IRL or print on a poster."

    def get_raw_price(self, state: dict) -> int:
        selected_model = state.get("selected_model", Text2ImgModels.dream_shaper.name)
        total = 5
        match selected_model:
            case Text2ImgModels.deepfloyd_if.name:
                total += 3
            case Text2ImgModels.dall_e.name:
                total += 10
        return total
