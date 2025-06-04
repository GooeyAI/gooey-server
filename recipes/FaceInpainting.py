import typing
from functools import partial

import requests
from pydantic import BaseModel

import gooey_gui as gui
from bots.models import Workflow
from daras_ai.extract_face import extract_and_reposition_face_cv2
from daras_ai.image_input import (
    upload_file_from_bytes,
    safe_filename,
)
from daras_ai_v2 import stable_diffusion
from daras_ai_v2.base import BasePage
from daras_ai_v2.extract_face import extract_face_img_bytes
from daras_ai_v2.pydantic_validation import HttpUrlStr
from daras_ai_v2.upscaler_models import gfpgan
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.img_model_settings_widgets import (
    img_model_settings,
)
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.repositioning import repositioning_preview_img
from daras_ai_v2.safety_checker import safety_checker
from daras_ai_v2.stable_diffusion import InpaintingModels


class FaceInpaintingPage(BasePage):
    title = "AI Image with a Face"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/10c2ce06-88da-11ee-b428-02420a000168/ai%20image%20with%20a%20face.png.png"
    workflow = Workflow.FACE_INPAINTING
    slug_versions = ["FaceInpainting", "face-in-ai-generated-photo"]

    sane_defaults = {
        "num_outputs": 1,
        "quality": 50,
        "output_width": 512,
        "output_height": 512,
        "guidance_scale": 7.5,
        "seed": 42,
        "upscale_factor": 1.0,
    }

    class RequestModel(BasePage.RequestModel):
        input_image: HttpUrlStr
        text_prompt: str

        face_scale: float | None = None
        face_pos_x: float | None = None
        face_pos_y: float | None = None

        selected_model: (
            typing.Literal[tuple(e.name for e in InpaintingModels)] | None
        ) = None

        negative_prompt: str | None = None

        num_outputs: int | None = None
        quality: int | None = None
        upscale_factor: float | None = None

        output_width: int | None = None
        output_height: int | None = None

        guidance_scale: float | None = None

        seed: int | None = None

    class ResponseModel(BaseModel):
        resized_image: HttpUrlStr
        face_mask: HttpUrlStr
        diffusion_images: list[HttpUrlStr]
        output_images: list[HttpUrlStr]

    def render_description(self):
        gui.write(
            """    
    This recipe takes a photo with a face and then uses the text prompt to paint a background.
    
    How It Works:
    
    1. Extracts faces from any image using MediaPipe
    2. Generates images from the given prompt and paints a background scene with Stable diffusion
    3. Improves faces using GFPGAN    
    
    *Face Inpainting: Photo > Face Masking > Stable Diffusion > GFPGAN*

    """
        )

    def render_form_v2(self):
        gui.text_area(
            """
            #### Prompt
            Describe the character that you'd like to generate. 
            """,
            key="text_prompt",
            placeholder="Iron man",
        )

        gui.file_uploader(
            """
            #### Face Photo
            Give us a photo of yourself, or anyone else
            """,
            key="input_image",
            accept=["image/*"],
        )

    def validate_form_v2(self):
        text_prompt = gui.session_state.get("text_prompt")
        input_image = gui.session_state.get("input_image")
        assert text_prompt and input_image, "Please provide a Prompt and a Face Photo"

    def render_settings(self):
        img_model_settings(InpaintingModels)

        col1, col2 = gui.columns(2)
        with col1:
            gui.slider(
                "##### Upscaling",
                min_value=1.0,
                max_value=4.0,
                step=0.5,
                key="upscale_factor",
            )

        gui.write("---")

        gui.write(
            """
            #### Face Repositioning Settings
            """
        )

        gui.write("How _big_ should the face look?")
        col1, _ = gui.columns(2)
        with col1:
            face_scale = gui.slider(
                "Scale",
                min_value=0.1,
                max_value=1.0,
                key="face_scale",
            )

        gui.write("_Where_ would you like to place the face in the scene?")
        col1, col2 = gui.columns(2)
        with col1:
            pos_x = gui.slider(
                "Position X",
                min_value=0.0,
                max_value=1.0,
                key="face_pos_x",
            )
        with col2:
            pos_y = gui.slider(
                "Position Y",
                min_value=0.0,
                max_value=1.0,
                key="face_pos_y",
            )

        import cv2

        # show an example image
        img_cv2 = cv2.imread("static/face.png")
        # extract face
        img, _ = extract_and_reposition_face_cv2(
            img_cv2,
            out_size=(
                gui.session_state["output_width"],
                gui.session_state["output_height"],
            ),
            out_face_scale=face_scale,
            out_pos_x=pos_x,
            out_pos_y=pos_y,
        )
        repositioning_preview_img(img)

    def render_output(self):
        output_images = gui.session_state.get("output_images")

        if output_images:
            gui.write("#### Output Image")
            for url in output_images:
                gui.image(url, show_download_button=True)
        else:
            gui.div()

    def render_steps(self):
        input_file = gui.session_state.get("input_file")
        input_image = gui.session_state.get("input_image")
        input_image_or_file = input_image or input_file
        output_images = gui.session_state.get("output_images")

        col1, col2, col3, col4 = gui.columns(4)

        with col1:
            if input_image_or_file:
                gui.image(input_image_or_file, caption="Input Image")
            else:
                gui.div()

        with col2:
            resized_image = gui.session_state.get("resized_image")
            if resized_image:
                gui.image(resized_image, caption="Repositioned Face")
            else:
                gui.div()

            face_mask = gui.session_state.get("face_mask")
            if face_mask:
                gui.image(face_mask, caption="Face Mask")
            else:
                gui.div()

        with col3:
            diffusion_images = gui.session_state.get("diffusion_images")
            if diffusion_images:
                for url in diffusion_images:
                    gui.image(url, caption="Generated Image")
            else:
                gui.div()

        with col4:
            if output_images:
                for url in output_images:
                    gui.image(url, caption="gfpgan - Face Restoration")
            else:
                gui.div()

    def render_usage_guide(self):
        youtube_video("To4Oc_d4Nus")
        # loom_video("788dfdee763a4e329e28e749239f9810")

    def run(self, state: dict):
        if not self.request.user.disable_safety_checker:
            yield "Running safety checker..."
            safety_checker(
                text=state["text_prompt"],
                image=state["input_image"],
            )

        yield "Extracting Face..."

        input_image_url = state["input_image"]
        img_bytes = requests.get(input_image_url).content

        re_img_bytes, face_mask_bytes = extract_face_img_bytes(
            img_bytes,
            out_size=(state["output_width"], state["output_height"]),
            face_scale=state["face_scale"],
            pos_x=state["face_pos_x"],
            pos_y=state["face_pos_y"],
        )

        state["resized_image"] = upload_file_from_bytes("re_img.png", re_img_bytes)
        state["face_mask"] = upload_file_from_bytes("face_mask.png", face_mask_bytes)

        yield "Generating Image..."

        prompt = state.get("text_prompt", "")

        diffusion_images = stable_diffusion.inpainting(
            selected_model=state["selected_model"],
            prompt=prompt,
            num_outputs=state.get("num_outputs", 1),
            edit_image=state["resized_image"],
            edit_image_bytes=re_img_bytes,
            mask=state["face_mask"],
            mask_bytes=face_mask_bytes,
            num_inference_steps=state.get("quality", 50),
            width=state["output_width"],
            height=state["output_height"],
            negative_prompt=state.get("negative_prompt"),
            guidance_scale=state.get("guidance_scale"),
            seed=state["seed"],
        )
        state["diffusion_images"] = diffusion_images

        yield "Running gfpgan..."

        output_images = map_parallel(
            partial(gfpgan, scale=state["upscale_factor"]),
            diffusion_images,
        )

        state["output_images"] = [
            upload_file_from_bytes(
                safe_filename(f"gooey.ai inpainting - {prompt.strip()}.png"),
                img_bytes,
                # requests.get(url).content,
            )
            for img_bytes in output_images
        ]

    def related_workflows(self) -> list:
        from recipes.SocialLookupEmail import SocialLookupEmailPage
        from recipes.EmailFaceInpainting import EmailFaceInpaintingPage
        from recipes.LipsyncTTS import LipsyncTTSPage
        from recipes.SEOSummary import SEOSummaryPage

        return [
            SocialLookupEmailPage,
            EmailFaceInpaintingPage,
            LipsyncTTSPage,
            SEOSummaryPage,
        ]

    def render_run_preview_output(self, state: dict):
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

    def get_raw_price(self, state: dict) -> int:
        selected_model = state.get("selected_model")
        match selected_model:
            case InpaintingModels.dall_e.name:
                unit_price = 20
            case _:
                unit_price = 5

        return unit_price * state.get("num_outputs", 1)
