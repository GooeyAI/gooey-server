import typing

import requests
from pydantic import BaseModel

import gooey_ui as st
from daras_ai_v2.base import BasePage
from daras_ai_v2.img_model_settings_widgets import img_model_settings
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.stable_diffusion import (
    InpaintingModels,
    Img2ImgModels,
    img2img,
    SD_IMG_MAX_SIZE,
    instruct_pix2pix,
    controlnet,
    ControlNetModels,
)


class Img2ImgPage(BasePage):
    title = "Edit An Image with AI prompt"
    slug_versions = ["Img2Img", "ai-photo-editor"]

    sane_defaults = {
        "num_outputs": 1,
        "quality": 50,
        "output_width": 512,
        "output_height": 512,
        "guidance_scale": 7.5,
        "prompt_strength": 0.4,
        # "sd_2_upscaling": False,
        "seed": 42,
        "image_guidance_scale": 1.2,
        "selected_controlnet_model": None,
    }

    class RequestModel(BaseModel):
        input_image: str
        text_prompt: str | None

        selected_model: typing.Literal[tuple(e.name for e in Img2ImgModels)] | None
        selected_controlnet_model: typing.Literal[
            tuple(e.name for e in ControlNetModels)
        ] | None
        negative_prompt: str | None

        num_outputs: int | None
        quality: int | None

        output_width: int | None
        output_height: int | None

        guidance_scale: float | None
        prompt_strength: float | None
        controlnet_conditioning_scale: float | None

        # sd_2_upscaling: bool | None

        seed: int | None

        image_guidance_scale: float | None

    class ResponseModel(BaseModel):
        output_images: list[str]

    def related_workflows(self) -> list:
        from recipes.ImageSegmentation import ImageSegmentationPage
        from recipes.ObjectInpainting import ObjectInpaintingPage
        from recipes.FaceInpainting import FaceInpaintingPage
        from recipes.CompareText2Img import CompareText2ImgPage

        return [
            ImageSegmentationPage,
            ObjectInpaintingPage,
            FaceInpaintingPage,
            CompareText2ImgPage,
        ]

    def render_form_v2(self):
        st.file_uploader(
            """
            ### Input Image
            """,
            key="input_image",
            upload_meta=dict(resize=f"{SD_IMG_MAX_SIZE[0] * SD_IMG_MAX_SIZE[1]}@>"),
        )

        if st.session_state.get("selected_model") != InpaintingModels.dall_e.name:
            st.text_area(
                """
                ### Prompt
                Describe your edits 
                """,
                key="text_prompt",
                placeholder="Iron man",
            )

    def validate_form_v2(self):
        input_image = st.session_state.get("input_image")
        assert input_image, "Please provide an Input Image"

    def render_description(self):
        st.write(
            """
            This recipe takes an image and a prompt and then attempts to alter the image, based on the text.

            Adjust the Prompt Strength in Settings to change how strongly the text should influence the image. 
            """
        )

    def render_settings(self):
        img_model_settings(Img2ImgModels)

    def render_usage_guide(self):
        youtube_video("narcZNyuNAg")

    def render_output(self):
        text_prompt = st.session_state.get("text_prompt", "")
        output_images = st.session_state.get("output_images", [])

        for img in output_images:
            st.image(img, caption="```" + text_prompt.replace("\n", "") + "```")

    def render_example(self, state: dict):
        col1, col2 = st.columns(2)
        with col2:
            output_images = state.get("output_images", [])
            for img in output_images:
                st.image(img, caption="Generated Image")
        with col1:
            input_image = state.get("input_image")
            st.image(input_image, caption="Input Image")
            st.write("**Prompt**")
            st.write("```properties\n" + state.get("text_prompt", "") + "\n```")

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: Img2ImgPage.RequestModel = self.RequestModel.parse_obj(state)

        init_image = request.input_image
        init_image_bytes = requests.get(init_image).content

        yield "Generating Image..."

        if request.selected_model == Img2ImgModels.instruct_pix2pix.name:
            state["output_images"] = instruct_pix2pix(
                prompt=request.text_prompt,
                num_outputs=request.num_outputs,
                num_inference_steps=request.quality,
                negative_prompt=request.negative_prompt,
                guidance_scale=request.guidance_scale,
                seed=request.seed,
                images=[init_image],
                image_guidance_scale=request.image_guidance_scale,
            )
        elif request.selected_controlnet_model:
            state["output_images"] = controlnet(
                selected_model=request.selected_model,
                selected_controlnet_model=request.selected_controlnet_model,
                prompt=request.text_prompt,
                num_outputs=request.num_outputs,
                init_image=init_image,
                num_inference_steps=request.quality,
                negative_prompt=request.negative_prompt,
                guidance_scale=request.guidance_scale,
                seed=request.seed,
                controlnet_conditioning_scale=request.controlnet_conditioning_scale,
            )
        else:
            state["output_images"] = img2img(
                selected_model=request.selected_model,
                prompt=request.text_prompt,
                num_outputs=request.num_outputs,
                init_image=init_image,
                init_image_bytes=init_image_bytes,
                num_inference_steps=request.quality,
                prompt_strength=request.prompt_strength,
                negative_prompt=request.negative_prompt,
                guidance_scale=request.guidance_scale,
                seed=request.seed,
            )

    def preview_description(self, state: dict) -> str:
        return "Add an image and a prompt and this workflow will alter the image using your text & the latest InstructPix2Pix or Stable Difussion Img2Img AI model."

    def get_raw_price(self, state: dict) -> int:
        selected_model = state.get("selected_model")
        match selected_model:
            case Img2ImgModels.dall_e.name:
                return 20
            case _:
                return 5
