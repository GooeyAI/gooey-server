import typing

from daras_ai_v2.pydantic_validation import FieldHttpUrl
import requests
from pydantic import BaseModel

import gooey_gui as gui
from bots.models import Workflow
from daras_ai.image_input import (
    upload_file_from_bytes,
    resize_img_scale,
    bytes_to_cv2_img,
    cv2_img_to_bytes,
)
from daras_ai_v2 import stable_diffusion
from daras_ai_v2.base import BasePage
from daras_ai_v2.image_segmentation import dis
from daras_ai_v2.img_model_settings_widgets import (
    img_model_settings,
)
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.repositioning import (
    reposition_object_img_bytes,
    repositioning_preview_widget,
)
from daras_ai_v2.stable_diffusion import InpaintingModels

DEFAULT_OBJECT_INPAINTING_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/4bca6982-9456-11ee-bc12-02420a0001cc/Product%20photo%20backgrounds.jpg.png"


class ObjectInpaintingPage(BasePage):
    title = "Generate Product Photo Backgrounds"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/f07b731e-88d9-11ee-a658-02420a000163/W.I.3.png.png"
    workflow = Workflow.OBJECT_INPAINTING
    slug_versions = ["ObjectInpainting", "product-photo-background-generator"]

    sane_defaults = {
        "mask_threshold": 0.7,
        "num_outputs": 1,
        "quality": 50,
        "output_width": 512,
        "output_height": 512,
        "guidance_scale": 7.5,
        "sd_2_upscaling": False,
        "seed": 42,
    }

    class RequestModel(BasePage.RequestModel):
        input_image: FieldHttpUrl
        text_prompt: str

        obj_scale: float | None
        obj_pos_x: float | None
        obj_pos_y: float | None

        mask_threshold: float | None

        selected_model: typing.Literal[tuple(e.name for e in InpaintingModels)] | None

        negative_prompt: str | None

        num_outputs: int | None
        quality: int | None

        output_width: int | None
        output_height: int | None

        guidance_scale: float | None

        sd_2_upscaling: bool | None

        seed: int | None

    class ResponseModel(BaseModel):
        resized_image: FieldHttpUrl
        obj_mask: FieldHttpUrl
        # diffusion_images: list[FieldHttpUrl]
        output_images: list[FieldHttpUrl]

    def preview_image(self, state: dict) -> str | None:
        return DEFAULT_OBJECT_INPAINTING_META_IMG

    def related_workflows(self) -> list:
        from recipes.ImageSegmentation import ImageSegmentationPage
        from recipes.GoogleImageGen import GoogleImageGenPage
        from recipes.CompareText2Img import CompareText2ImgPage
        from recipes.Img2Img import Img2ImgPage

        return [
            ImageSegmentationPage,
            GoogleImageGenPage,
            CompareText2ImgPage,
            Img2ImgPage,
        ]

    def render_form_v2(self):
        gui.text_area(
            """
            #### Prompt
            Describe the scene that you'd like to generate. 
            """,
            key="text_prompt",
            placeholder="Iron man",
        )

        gui.file_uploader(
            """
            #### Object Photo
            Give us a photo of anything
            """,
            key="input_image",
        )

    def validate_form_v2(self):
        text_prompt = gui.session_state.get("text_prompt", "").strip()
        input_image = gui.session_state.get("input_image")
        assert text_prompt and input_image, "Please provide a Prompt and a Object Photo"

    def render_description(self):
        gui.write(
            """
            This recipe an image of an object, masks it and then renders the background around the object according to the prompt. 
            
            How It Works:
            1. Takes an image
            2. Attempts to find an object in the image
            3. Masks the object
            4. Adjusts the X/Y position and zoom according to the settings
            5. Draws the background around the object according to the prompt.
            """
        )

    def render_settings(self):
        img_model_settings(InpaintingModels)

        gui.write("---")

        gui.write(
            """
            #### Object Repositioning Settings
            """
        )

        gui.write("How _big_ should the object look?")
        col1, _ = gui.columns(2)
        with col1:
            obj_scale = gui.slider(
                "Scale",
                min_value=0.1,
                max_value=1.0,
                key="obj_scale",
            )

        gui.write("_Where_ would you like to place the object in the scene?")
        col1, col2 = gui.columns(2)
        with col1:
            pos_x = gui.slider(
                "Position X",
                min_value=0.0,
                max_value=1.0,
                key="obj_pos_x",
            )
        with col2:
            pos_y = gui.slider(
                "Position Y",
                min_value=0.0,
                max_value=1.0,
                key="obj_pos_y",
            )

        import cv2

        # show an example image
        img_cv2 = cv2.imread("static/obj.png")
        mask_cv2 = cv2.imread("static/obj_mask.png")

        repositioning_preview_widget(
            img_cv2=img_cv2,
            mask_cv2=mask_cv2,
            obj_scale=obj_scale,
            pos_x=pos_x,
            pos_y=pos_y,
            out_size=(
                gui.session_state["output_width"],
                gui.session_state["output_height"],
            ),
        )

        gui.slider(
            """
            ##### Edge Threshold
            Helps to remove edge artifacts. `0` will turn this off. `0.9` will aggressively cut down edges. 
            """,
            min_value=0.0,
            max_value=0.9,
            key="mask_threshold",
        )

    def render_output(self):
        text_prompt = gui.session_state.get("text_prompt", "")
        output_images = gui.session_state.get("output_images")

        if output_images:
            for url in output_images:
                gui.image(url, caption=f"{text_prompt}", show_download_button=True)
        else:
            gui.div()

    def render_steps(self):
        input_file = gui.session_state.get("input_file")
        input_image = gui.session_state.get("input_image")
        input_image_or_file = input_image or input_file
        col1, col2, col3 = gui.columns(3)

        with col1:
            if input_image_or_file:
                gui.image(input_image_or_file, caption="Input Image")
            else:
                gui.div()

        with col2:
            resized_image = gui.session_state.get("resized_image")
            if resized_image:
                gui.image(resized_image, caption="Repositioned Object")
            else:
                gui.div()

            obj_mask = gui.session_state.get("obj_mask")
            if obj_mask:
                gui.image(obj_mask, caption="Object Mask")
            else:
                gui.div()

        with col3:
            diffusion_images = gui.session_state.get("output_images")
            if diffusion_images:
                for url in diffusion_images:
                    gui.image(url, caption=f"Generated Image")
            else:
                gui.div()

    def run(self, state: dict):
        request: ObjectInpaintingPage.RequestModel = self.RequestModel.parse_obj(state)

        yield "Running Image Segmentation..."

        img_bytes = requests.get(request.input_image).content

        padded_img_bytes = resize_img_scale(
            img_bytes,
            (request.output_width, request.output_height),
        )
        padded_img_url = upload_file_from_bytes("padded_img.png", padded_img_bytes)

        obj_mask_bytes = dis(padded_img_url)

        mask_cv2 = bytes_to_cv2_img(obj_mask_bytes)
        threshold_value = int(255 * request.mask_threshold)
        mask_cv2[mask_cv2 < threshold_value] = 0
        obj_mask_bytes = cv2_img_to_bytes(mask_cv2)

        yield "Repositioning..."

        re_img_bytes, re_mask_bytes = reposition_object_img_bytes(
            img_bytes=padded_img_bytes,
            mask_bytes=obj_mask_bytes,
            out_size=(request.output_width, request.output_height),
            out_obj_scale=request.obj_scale,
            out_pos_x=request.obj_pos_x,
            out_pos_y=request.obj_pos_y,
        )

        state["resized_image"] = upload_file_from_bytes("re_img.png", re_img_bytes)
        state["obj_mask"] = upload_file_from_bytes("obj_mask.png", re_mask_bytes)

        yield f"Generating Image..."

        diffusion_images = stable_diffusion.inpainting(
            selected_model=request.selected_model,
            prompt=request.text_prompt,
            num_outputs=request.num_outputs,
            edit_image=state["resized_image"],
            edit_image_bytes=re_img_bytes,
            mask=state["obj_mask"],
            mask_bytes=re_mask_bytes,
            num_inference_steps=request.quality,
            width=request.output_width,
            height=request.output_height,
            negative_prompt=request.negative_prompt,
            guidance_scale=request.guidance_scale,
            seed=request.seed,
        )
        state["output_images"] = diffusion_images

    def render_example(self, state: dict):
        col1, col2 = gui.columns(2)
        with col2:
            output_images = state.get("output_images")
            if output_images:
                for img in output_images:
                    gui.image(img, caption="Generated Image")
        with col1:
            input_image = state.get("input_image")
            gui.image(input_image, caption="Input Image")
            gui.write("**Prompt**")
            gui.write("```properties\n" + state.get("text_prompt", "") + "\n```")

    def preview_description(self, state: dict) -> str:
        return "Upload your product photo and describe the background. Then use Stable Diffusion's Inpainting AI to create professional background scenery without the photoshoot."

    def render_usage_guide(self):
        youtube_video("to6_17XJeck")

    def get_raw_price(self, state: dict) -> int:
        selected_model = state.get("selected_model")
        match selected_model:
            case InpaintingModels.dall_e.name:
                unit_price = 20
            case _:
                unit_price = 5

        return unit_price * state.get("num_outputs", 1)
