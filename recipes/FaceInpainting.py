import typing
from functools import partial

import requests
from pydantic import BaseModel

import gooey_ui as st
from daras_ai.extract_face import extract_and_reposition_face_cv2
from daras_ai.image_input import (
    upload_file_from_bytes,
    safe_filename,
)
from daras_ai_v2 import stable_diffusion
from daras_ai_v2.base import BasePage
from daras_ai_v2.extract_face import extract_face_img_bytes
from daras_ai_v2.face_restoration import map_parallel, gfpgan
from daras_ai_v2.img_model_settings_widgets import (
    img_model_settings,
)
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.stable_diffusion import InpaintingModels


class FaceInpaintingPage(BasePage):
    title = "AI Image with a Face"
    slug_versions = ["FaceInpainting", "face-in-ai-generated-photo"]
    version = 2

    sane_defaults = {
        "num_outputs": 1,
        "quality": 50,
        "output_width": 512,
        "output_height": 512,
        "guidance_scale": 7.5,
        "seed": 42,
        "upscale_factor": 1.0,
    }

    class RequestModel(BaseModel):
        input_image: str
        text_prompt: str

        face_scale: float | None
        face_pos_x: float | None
        face_pos_y: float | None

        selected_model: typing.Literal[tuple(e.name for e in InpaintingModels)] | None

        negative_prompt: str | None

        num_outputs: int | None
        quality: int | None
        upscale_factor: float | None

        output_width: int | None
        output_height: int | None

        guidance_scale: float | None

        seed: int | None

        class Config:
            schema_extra = {
                "example": {
                    "text_prompt": "tony stark from the iron man",
                    "input_photo": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/2bcf31e8-48ef-11ed-8fe1-02420a00005c/_DSC0030_1.jpg",
                }
            }

    class ResponseModel(BaseModel):
        resized_image: str
        face_mask: str
        diffusion_images: list[str]
        output_images: list[str]

    def preview_description(self, state: dict) -> str:
        return "Upload & extract a face into an AI-generated photo using your text + the latest Stable Diffusion or DallE image generator."

    def render_description(self):
        st.write(
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
        st.text_area(
            """
            ### Prompt
            Describe the character that you'd like to generate. 
            """,
            key="text_prompt",
            placeholder="Iron man",
        )

        st.file_uploader(
            """
            ### Face Photo
            Give us a photo of yourself, or anyone else
            """,
            key="input_image",
            accept=["image/*"],
        )

    def validate_form_v2(self):
        text_prompt = st.session_state.get("text_prompt")
        input_image = st.session_state.get("input_image")
        assert text_prompt and input_image, "Please provide a Prompt and a Face Photo"

    def render_settings(self):
        img_model_settings(InpaintingModels)

        col1, col2 = st.columns(2)
        with col1:
            st.slider(
                "##### Upscaling",
                min_value=1.0,
                max_value=4.0,
                step=0.5,
                key="upscale_factor",
            )

        st.write("---")

        st.write(
            """
            ### Face Repositioning Settings
            """
        )

        st.write("How _big_ should the face look?")
        col1, _ = st.columns(2)
        with col1:
            face_scale = st.slider(
                "Scale",
                min_value=0.1,
                max_value=1.0,
                key="face_scale",
            )

        st.write("_Where_ would you like to place the face in the scene?")
        col1, col2 = st.columns(2)
        with col1:
            pos_x = st.slider(
                "Position X",
                min_value=0.0,
                max_value=1.0,
                key="face_pos_x",
            )
        with col2:
            pos_y = st.slider(
                "Position Y",
                min_value=0.0,
                max_value=1.0,
                key="face_pos_y",
            )

        import cv2

        # show an example image
        img_cv2 = cv2.imread("static/face.png")

        # extract face
        img, mask = extract_and_reposition_face_cv2(
            img_cv2,
            out_size=(
                st.session_state["output_width"],
                st.session_state["output_height"],
            ),
            out_face_scale=face_scale,
            out_pos_x=pos_x,
            out_pos_y=pos_y,
        )

        # draw rule of 3rds
        color = (200, 200, 200)
        stroke = 2
        img_y, img_x, _ = img.shape
        for i in range(2):
            pos = (img_y // 3) * (i + 1)
            cv2.line(img, (0, pos), (img_x, pos), color, stroke)

            pos = (img_x // 3) * (i + 1)
            cv2.line(img, (pos, 0), (pos, img_y), color, stroke)

        st.image(img, width=300)

    def render_output(self):
        text_prompt = st.session_state.get("text_prompt", "")
        output_images = st.session_state.get("output_images")

        if output_images:
            for url in output_images:
                st.image(
                    url,
                    caption="```" + text_prompt.replace("\n", "") + "```",
                )
        else:
            st.div()

    def render_steps(self):
        input_file = st.session_state.get("input_file")
        input_image = st.session_state.get("input_image")
        input_image_or_file = input_image or input_file
        output_images = st.session_state.get("output_images")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            if input_image_or_file:
                st.image(input_image_or_file, caption="Input Image")
            else:
                st.div()

        with col2:
            resized_image = st.session_state.get("resized_image")
            if resized_image:
                st.image(resized_image, caption="Repositioned Face")
            else:
                st.div()

            face_mask = st.session_state.get("face_mask")
            if face_mask:
                st.image(face_mask, caption="Face Mask")
            else:
                st.div()

        with col3:
            diffusion_images = st.session_state.get("diffusion_images")
            if diffusion_images:
                for url in diffusion_images:
                    st.image(url, caption="Generated Image")
            else:
                st.div()

        with col4:
            if output_images:
                for url in output_images:
                    st.image(url, caption="gfpgan - Face Restoration")
            else:
                st.div()

    def render_usage_guide(self):
        youtube_video("To4Oc_d4Nus")
        # loom_video("788dfdee763a4e329e28e749239f9810")

    def run(self, state: dict):
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

        yield f"Generating Image..."

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

    def render_example(self, state: dict):
        col1, col2 = st.columns(2)
        with col2:
            output_images = state.get("output_images")
            if output_images:
                for img in output_images:
                    st.image(img, caption="Generated Image")
        with col1:
            input_image = state.get("input_image")
            st.image(input_image, caption="Input Image")
            st.write("**Prompt**")
            st.write("```properties\n" + state.get("text_prompt", "") + "\n```")

    def get_raw_price(self, state: dict) -> int:
        selected_model = state.get("selected_model")
        match selected_model:
            case InpaintingModels.dall_e.name:
                return 20
            case _:
                return 5
