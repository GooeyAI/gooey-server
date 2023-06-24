import typing

from furl import furl
from pydantic import BaseModel

import gooey_ui as st
from daras_ai_v2 import settings
from daras_ai_v2.base import BasePage
from daras_ai_v2.enum_selector_widget import enum_multiselect
from daras_ai_v2.img_model_settings_widgets import (
    guidance_scale_setting,
    output_resolution_setting,
    instruct_pix2pix_settings,
    sd_2_upscaling_setting,
    controlnet_weight_setting,
)
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.stable_diffusion import (
    Text2ImgModels,
    text2img,
    instruct_pix2pix,
    sd_upscale,
)


class QRCodeGeneratorPage(BasePage):
    title = "Create AI Art QR Codes...FAST"
    slug_versions = [
        "art-qr-code",
        "qr",
        "qr-code",
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
            key="text_prompt",
            placeholder="https://www.gooey.ai",
        )
        st.text_area(
            """
            ### 👩‍💻 Prompt
            Describe the subject/scene of the qr code. Some prompts blend better with qr codes than others.
            """,
            key="text_prompt",
            placeholder="Bright sunshine coming through the cracks of a wet, cave wall of big rocks",
        )

    def validate_form_v2(self):
        assert st.session_state["text_prompt"], "Please provide a prompt"

    def render_description(self):
        st.markdown(
            """
            This recipe takes any text and renders an image using multiple Text2Image engines.
            Use it to understand which image generator e.g. DallE or Stable Diffusion is best for your particular prompt.

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
        st.caption(
            """
            You can also enable ‘Edit Instructions’ to use InstructPix2Pix that allows you to change your generated output with a follow-up written instruction.
            """
        )
        if st.checkbox("📝 Edit Instructions"):
            st.text_area(
                """
                Describe how you want to change the generated qr code using [InstructPix2Pix](https://www.timothybrooks.com/instruct-pix2pix).
                """,
                key="__edit_instruction",
                placeholder="make the qr code blend in more with the background",
            )
        st.session_state["edit_instruction"] = st.session_state.get(
            "__edit_instruction"
        )
        st.text_area(
            """
            ##### 🧽 Negative Prompt
            List keywords that you DON'T want to see in your qr code.
            """,
            key="negative_prompt",
            placeholder="ugly, disfigured, low quality, blurry, nsfw",
        )
        output_resolution_setting()
        sd_2_upscaling_setting()
        col1, col2 = st.columns(2)
        with col1:
            guidance_scale_setting()
        with col2:
            if st.session_state.get("edit_instruction"):
                instruct_pix2pix_settings()
            controlnet_weight_setting(
                control_effect="make the qr code darker and background lighter (contrast helps qr readers)",
                model_type="Brightness",
                scale=(0.0, 0.7),
            )
            controlnet_weight_setting(
                control_effect="preserve small details mainly in the qr code which makes it more readable",
                model_type="Tiles",
                scale=(0.0, 2.0),
            )

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
        return "Enter your URL (or text) and an image prompt and we'll generate an arty QR code with your artistic style and content in about 30 seconds. This is a rad way to advertise your website in IRL or print on a poster."

    def get_raw_price(self, state: dict) -> int:
        return 5
