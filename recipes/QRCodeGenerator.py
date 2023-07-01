import typing

import numpy as np
import qrcode
import requests
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from furl import furl
from pydantic import BaseModel
from pyzbar import pyzbar

import gooey_ui as st
from daras_ai.image_input import (
    upload_file_from_bytes,
    bytes_to_cv2_img,
    cv2_img_to_bytes,
)
from daras_ai_v2.base import BasePage
from daras_ai_v2.descriptions import prompting101
from daras_ai_v2.img_model_settings_widgets import (
    output_resolution_setting,
    img_model_settings,
)
from daras_ai_v2.repositioning import reposition_object, repositioning_preview_widget
from daras_ai_v2.stable_diffusion import (
    Text2ImgModels,
    controlnet,
    ControlNetModels,
    Img2ImgModels,
    Schedulers,
)

ATTEMPTS = 1


class QRCodeGeneratorPage(BasePage):
    title = "AI Art QR Code"
    slug_versions = ["art-qr-code", "qr", "qr-code"]

    sane_defaults = dict(
        num_outputs=1,
        obj_scale=0.65,
        obj_pos_x=0.5,
        obj_pos_y=0.5,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__.update(self.sane_defaults)

    class RequestModel(BaseModel):
        qr_code_data: str | None
        qr_code_input_image: str | None

        use_url_shortener: bool | None

        text_prompt: str
        negative_prompt: str | None

        selected_model: typing.Literal[tuple(e.name for e in Text2ImgModels)] | None
        selected_controlnet_model: list[
            typing.Literal[tuple(e.name for e in ControlNetModels)], ...
        ] | None

        output_width: int | None
        output_height: int | None

        guidance_scale: float | None
        controlnet_conditioning_scale: typing.List[float] | None

        num_outputs: int | None
        quality: int | None
        scheduler: typing.Literal[tuple(e.name for e in Schedulers)] | None

        seed: int | None

        obj_scale: float | None
        obj_pos_x: float | None
        obj_pos_y: float | None

    class ResponseModel(BaseModel):
        output_images: list[str]
        raw_images: list[str]
        shortened_url: str | None
        cleaned_qr_code: str

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
            ### 👩‍💻 Prompt
            Describe the subject/scene of the qr code. Some prompts blend better with qr codes than others.
            """,
            key="text_prompt",
            placeholder="Bright sunshine coming through the cracks of a wet, cave wall of big rocks",
        )

        st.session_state.setdefault(
            "__enable_qr_code_input_image",
            bool(st.session_state.get("qr_code_input_image")),
        )
        if st.checkbox(
            f"Upload an existing QR Code", key="__enable_qr_code_input_image"
        ):
            st.file_uploader(
                """
                ### 📷 QR Code Image
                It will be reformatted and cleaned
                """,
                key="qr_code_input_image",
                accept=["image/*"],
            )
            st.session_state["qr_code_data"] = None
        else:
            st.text_area(
                """
                ### 🔗 URL
                Enter a URL or text. Generally, shorter is better.
                """,
                key="qr_code_data",
                placeholder="https://www.gooey.ai",
            )
            st.session_state["qr_code_input_image"] = None

    def validate_form_v2(self):
        assert st.session_state["text_prompt"], "Please provide a prompt"

        qr_code_data = st.session_state.get("qr_code_data")
        qr_code_input_image = st.session_state.get("qr_code_input_image")
        assert (
            qr_code_data or qr_code_input_image
        ), "Please provide QR Code URL, text content, or upload an image"

    def render_description(self):
        st.markdown(
            """
            Enter your URL (or text) and an image prompt and we'll generate an arty QR code with your artistic style and content in about 30 seconds. This is a rad way to advertise your website in IRL or print on a poster.
            It is made possible by the open source [Control Net](https://github.com/lllyasviel/ControlNet).
            """
        )
        prompting101()

    def render_steps(self):
        shortened_url = st.session_state.get("shortened_url", False)
        if shortened_url:
            st.markdown(
                f"""
                #### Shorten the URL
                For more aesthetic and reliable QR codes with fewer black squares, we automatically shorten the URL: {shortened_url}
                """
            )
        img = st.session_state.get("cleaned_qr_code")
        if img:
            st.image(
                img,
                caption="""
                #### Generate clean QR code
                Having consistent padding, formatting, and using high error correction in the QR Code encoding makes the QR code more readable and robust to damage and thus yields more reliable results with the model.
                """,
            )
        raw_images = st.session_state.get("raw_images", [])
        if raw_images:
            st.markdown(
                """
#### Generate the QR Codes
We use the model and controlnet constraints to generate QR codes that blend the prompt with the cleaned QR Code. We generate them one at a time and check if they work. If they don't work, we try again. If they work, we stop.

Here are the attempts:
                """
            )
        for img in raw_images:
            st.image(img)
        output_images = st.session_state.get("output_images", [])
        if output_images:
            st.markdown(
                """
#### Run quality control
We programatically scan the QR Codes to make sure they are readable. Once a working one is found, it becomes the output.

Here is the final output:
                """
            )
        for img in output_images:
            st.image(img)

    def render_settings(self):
        st.write(
            """
            Customize the QR Code output for your text prompt with these Settings. 
            """
        )

        st.checkbox("🔗 URL Shortener", key="use_url_shortener")
        st.caption("Enabling this will automatically shorten URLs")

        img_model_settings(
            Img2ImgModels,
            show_scheduler=True,
            require_controlnet=True,
            extra_explanations={
                ControlNetModels.sd_controlnet_tile: "Tiling: Preserves small details mainly in the qr code which makes it more readable",
                ControlNetModels.sd_controlnet_brightness: "Brightness: Makes the qr code darker and background lighter (contrast helps qr readers)",
            },
        )
        st.write("---")

        output_resolution_setting()

        st.write(
            """
            ##### ⌖ Positioning
            Use this to control where the QR code is placed in the image, and how big it should be.
            """,
            className="gui-input",
        )
        col1, _ = st.columns(2)
        with col1:
            obj_scale = st.slider(
                "Scale",
                min_value=0.1,
                max_value=1.0,
                step=0.05,
                key="obj_scale",
            )
        col1, col2 = st.columns(2, responsive=False)
        with col1:
            pos_x = st.slider(
                "Position X",
                min_value=0.0,
                max_value=1.0,
                step=0.05,
                key="obj_pos_x",
            )
        with col2:
            pos_y = st.slider(
                "Position Y",
                min_value=0.0,
                max_value=1.0,
                step=0.05,
                key="obj_pos_y",
            )

        img_cv2 = mask_cv2 = np.array(
            qrcode.QRCode(border=0).make_image().convert("RGB")
        )
        repositioning_preview_widget(
            img_cv2=img_cv2,
            mask_cv2=mask_cv2,
            obj_scale=obj_scale,
            pos_x=pos_x,
            pos_y=pos_y,
            out_size=(
                st.session_state["output_width"],
                st.session_state["output_height"],
            ),
            color=255,
        )

    def render_output(self):
        state = st.session_state
        self._render_outputs(state)

    def _render_outputs(self, state: dict):
        for img in state.get("output_images", []):
            st.image(img)
            st.caption(f'{state.get("qr_code_data")}')

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: QRCodeGeneratorPage.RequestModel = self.RequestModel.parse_obj(state)

        yield "Generating QR Code..."
        image, qr_code_data, did_shorten = generate_and_upload_qr_code(request)
        if did_shorten:
            state["shortened_url"] = qr_code_data
        state["cleaned_qr_code"] = image

        state["raw_images"] = raw_images = []

        yield f"Running {Text2ImgModels[request.selected_model].value}..."
        state["output_images"] = controlnet(
            selected_model=request.selected_model,
            selected_controlnet_model=request.selected_controlnet_model,
            prompt=request.text_prompt,
            init_image=image,
            num_outputs=request.num_outputs,
            num_inference_steps=request.quality,
            negative_prompt=request.negative_prompt,
            guidance_scale=request.guidance_scale,
            seed=request.seed,
            controlnet_conditioning_scale=request.controlnet_conditioning_scale,
            scheduler=request.scheduler,
        )

        # TODO: properly detect bad qr code
        # TODO: generate safe qr code instead
        # for attempt in images:
        #     raw_images.append(attempt)
        #     try:
        #         assert download_qr_code_data(attempt) == qr_code_data
        #     except InvalidQRCode:
        #         continue
        #     state["output_images"] = [attempt]
        #     break
        # raise RuntimeError(
        #     'Doh! That didn\'t work. Sometimes the AI produces bad QR codes. Please press "Regenerate" to try again.'
        # )

    def render_example(self, state: dict):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(
                f"""
                ```text
                {state.get("text_prompt", "")}
                ```
                """
            )
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


def generate_and_upload_qr_code(request: QRCodeGeneratorPage.RequestModel):
    qr_code_data = request.qr_code_data
    if not qr_code_data:
        qr_code_input_image = request.qr_code_input_image
        if not qr_code_input_image:
            raise ValueError("Please provide QR Code URL, text content, or an image")
        qr_code_data = download_qr_code_data(qr_code_input_image)
    qr_code_data = qr_code_data.strip()

    should_shorten = request.use_url_shortener and qr_code_data.startswith("http")
    if should_shorten:
        qr_code_data, should_shorten = shorten_url(qr_code_data)

    img_cv2 = generate_qr_code(qr_code_data)

    img_cv2, _ = reposition_object(
        orig_img=img_cv2,
        orig_mask=img_cv2,
        out_size=(request.output_width, request.output_height),
        out_obj_scale=request.obj_scale,
        out_pos_x=request.obj_pos_x,
        out_pos_y=request.obj_pos_y,
        color=255,
    )

    img_url = upload_file_from_bytes("cleaned_qr.png", cv2_img_to_bytes(img_cv2))
    return img_url, qr_code_data, should_shorten


def generate_qr_code(qr_code_data: str) -> np.ndarray:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, border=0)
    qr.add_data(qr_code_data)
    return np.array(qr.make_image().convert("RGB"))


def shorten_url(qr_code_data: str) -> tuple[str, bool]:
    try:
        r = requests.get(
            furl(
                "https://is.gd/create.php",
                query_params={"format": "simple", "url": qr_code_data},
            ).url,
            timeout=2.50,
        )
        r.raise_for_status()
        # Validate that the response is a URL
        try:
            URLValidator()(r.text)
        except ValidationError:
            pass
        else:
            return r.text, True
    except requests.RequestException as e:
        print(f"ignoring shortened url error: {e}")
        pass  # We can keep going without the shortened url and just use the original url
    return qr_code_data, False


def download_qr_code_data(url: str) -> str:
    r = requests.get(url)
    r.raise_for_status()
    img = bytes_to_cv2_img(r.content, greyscale=True)
    return extract_qr_code_data(img)


def extract_qr_code_data(img: np.ndarray) -> str:
    decoded = pyzbar.decode(img)
    if not (decoded and decoded[0]):
        raise InvalidQRCode("No QR code found in image")
    info = decoded[0].data.decode()
    if not info:
        raise InvalidQRCode("No data found in QR code")
    return info


class InvalidQRCode(AssertionError):
    pass
