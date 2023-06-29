import typing

import requests
import qrcode
import numpy as np
import urllib
import cv2
import PIL.Image as Image
from daras_ai.image_input import upload_file_from_bytes

from pydantic import BaseModel

import gooey_ui as st
from daras_ai_v2 import db
from daras_ai_v2.base import BasePage
from daras_ai_v2.img_model_settings_widgets import (
    guidance_scale_setting,
    model_selector,
    controlnet_settings,
    output_resolution_setting,
)
from daras_ai_v2.descriptions import prompting101
from daras_ai_v2.stable_diffusion import (
    Text2ImgModels,
    controlnet,
    ControlNetModels,
    controlnet_model_explanations,
    text2img_model_ids,
)

controlnet_model_explanations = {
    ControlNetModels.sd_controlnet_tile: "preserve small details mainly in the qr code which makes it more readable",
    ControlNetModels.sd_controlnet_brightness: "make the qr code darker and background lighter (contrast helps qr readers)",
}


ATTEMPTS = 2
DEFAULT_SIZE = 512


class QRCodeGeneratorPage(BasePage):
    title = "AI Art QR Code"
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
        "output_width": DEFAULT_SIZE,
        "output_height": DEFAULT_SIZE,
        "num_inference_steps": 100,
        "guidance_scale": 9,
        "controlnet_conditioning_scale": [0.25, 0.45],
        "seed": 1331,
        "negative_prompt": "ugly, disfigured, low quality, blurry, nsfw, text, words",
        "use_image_input": False,
        "use_url_shortener": True,
    }

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
        selected_controlnet_model: typing.Tuple[
            typing.Literal[tuple(e.name for e in ControlNetModels)], ...
        ] | None

        output_width: int | None
        output_height: int | None

        guidance_scale: float | None
        controlnet_conditioning_scale: typing.List[float] | None

        # num_images: int | None
        num_inference_steps: int | None
        scheduler: str | None

        seed: int | None

    class ResponseModel(BaseModel):
        output_image: str
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
        if not st.session_state.get("qr_code_data", False) and st.session_state.get(
            "qr_code_input_image", False
        ):
            st.session_state["use_image_input"] = True
        if not st.session_state.get("use_image_input", False):
            st.text_area(
                """
                ### 🔗 URL
                Enter your URL, link or text. Generally shorter is better. We automatically shorten URLs that start with http or https.
                """,
                key="qr_code_data",
                placeholder="https://www.gooey.ai",
            )
        if st.checkbox(
            f"{'-- OR -- ' if not st.session_state.get('use_image_input', False) else ''}Upload an existing qr code.",
            key="use_image_input",
        ):
            st.file_uploader(
                """
                It will be reformatted and cleaned and used instead of the URL field.
                """,
                key="qr_code_input_image",
                accept=["image/*"],
            )
            st.session_state["qr_code_data"] = None
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
        assert st.session_state.get("qr_code_data") or st.session_state.get(
            "qr_code_input_image"
        ), "Please provide QR Code URL, text content, or upload an image"
        if not st.session_state.get("qr_code_data") and st.session_state.get(
            "qr_code_input_image"
        ):
            req = urllib.request.urlopen(st.session_state.get("qr_code_input_image"))
            arr = np.asarray(bytearray(req.read()), dtype=np.uint8)
            img = cv2.imdecode(arr, -1)
            (
                retval,
                decoded_info,
                points,
                straight_qrcode,
            ) = cv2.QRCodeDetector().detectAndDecodeMulti(img)
            assert (
                retval and decoded_info[0]
            ), "Please upload a valid QR Code image that is readable"

    def render_description(self):
        st.markdown(
            """
            Enter your URL (or text) and an image prompt and we'll generate an arty QR code with your artistic style and content in about 30 seconds. This is a rad way to advertise your website in IRL or print on a poster.
            It is made possible by the open source [Control Net](https://github.com/lllyasviel/ControlNet).
            """
        )
        prompting101()

    def render_steps(self):
        if not st.session_state.get("raw_images"):
            st.markdown(
                """
                #### Generate the QR Code to see steps
                """
            )
            return
        shortened_url = st.session_state.get("shortened_url", False)
        if shortened_url:
            st.markdown(
                f"""
                #### Shorten the URL
                For more aesthetic and reliable QR codes with fewer black squares, we automatically shorten the URL: {shortened_url}
                """
            )
        st.markdown(
            """
            #### Generate clean QR code
            Having consistent padding, formatting, and using high error correction in the QR Code encoding makes the QR code more readable and robust to damage and thus yields more reliable results with the model.
            """
        )
        img = st.session_state.get("cleaned_qr_code")
        if img:
            st.image(img)
        st.markdown(
            """
            #### Generate the QR Codes
            We use the model and controlnet constraints to generate QR codes that blend the prompt with the cleaned QR Code. We generate them one at a time and check if they work. If they don't work, we try again. If they work, we stop.
            
            Here are the attempts:
            """
        )
        for imgsrc in st.session_state.get("raw_images", []):
            st.image(imgsrc)
        st.markdown(
            """
            #### Run quality control
            We programatically scan the QR Codes to make sure they are readable. Once a working one is found, it becomes the output.

            Here is the final output:
            """
        )
        for imgsrc in [st.session_state["output_image"]]:
            st.image(imgsrc)

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
        output_resolution_setting()
        col1, col2 = st.columns(2)
        with col1:
            st.caption(
                """
            ### 🤖 Generative Model
            Choose the model responsible for generating the content around the qr code.
            """
            )
            model_selector(Text2ImgModels, same_line=False, require_controlnet=True)
            guidance_scale_setting()
        with col2:
            st.checkbox(
                """
                ### 🔗 URL Shortener
                """,
                key="use_url_shortener",
            )
            st.caption(
                "Check to automatically shorten URLs that start with http or https."
            )
            controlnet_settings(controlnet_model_explanations)

    def render_output(self):
        state = st.session_state
        self._render_outputs(state)

    def _render_outputs(self, state: dict):
        for img in [state.get("output_image")]:
            st.image(img, caption=state.get("qr_code_data"))

    def run(self, state: dict) -> typing.Iterator[str | None]:
        for key, val in state.items():
            state[key] = tuple(val) if isinstance(val, list) else val

        request: QRCodeGeneratorPage.RequestModel = self.RequestModel.parse_obj(state)
        image, qr_code_data = self.preprocess_qr_code(request.dict())
        if request.dict().get("use_url_shortener", True) and qr_code_data.startswith(
            "http"
        ):
            state["shortened_url"] = qr_code_data
        state["cleaned_qr_code"] = image

        state["output_image"] = None
        state["raw_images"] = []

        selected_model = request.selected_model
        yield f"Running {Text2ImgModels[selected_model].value}..."

        for i in range(ATTEMPTS):
            attempt = controlnet(
                selected_model=selected_model,
                selected_controlnet_models=request.selected_controlnet_model,
                prompt=request.text_prompt,
                num_outputs=1,
                init_image=image,
                width=request.output_width,
                height=request.output_height,
                num_inference_steps=request.num_inference_steps,
                negative_prompt=request.negative_prompt,
                guidance_scale=request.guidance_scale,
                seed=request.seed + i,
                controlnet_conditioning_scale=request.controlnet_conditioning_scale,
                scheduler=request.scheduler,
                selected_models_enum=Text2ImgModels,
                selected_models_ids=text2img_model_ids,
            )[0]
            state["raw_images"].append(attempt)

            req = urllib.request.urlopen(attempt)
            arr = np.asarray(bytearray(req.read()), dtype=np.uint8)
            img = cv2.imdecode(arr, -1)
            (
                retval,
                decoded_info,
                points,
                straight_qrcode,
            ) = cv2.QRCodeDetector().detectAndDecodeMulti(img)
            print(retval, decoded_info)
            if retval and (decoded_info[0] == qr_code_data or i == ATTEMPTS - 1):
                state["output_image"] = attempt
                break  # don't keep trying once we have a working QR code

        if not state["output_image"]:  # TODO: generate safe qr code instead
            state["output_image"] = state["raw_images"][0]

    def preprocess_qr_code(self, request: dict):
        qr_code_data = request.get("qr_code_data")
        qr_code_input_image = request.get("qr_code_input_image")
        width = request.get("output_width", DEFAULT_SIZE)
        height = request.get("output_height", DEFAULT_SIZE)
        if not qr_code_data:
            if not qr_code_input_image:
                raise ValueError(
                    "Please provide QR Code URL, text content, or an image"
                )
            req = urllib.request.urlopen(qr_code_input_image)
            arr = np.asarray(bytearray(req.read()), dtype=np.uint8)
            img = cv2.imdecode(arr, -1)
            (
                retval,
                decoded_info,
                points,
                straight_qrcode,
            ) = cv2.QRCodeDetector().detectAndDecodeMulti(img)
            qr_code_data = decoded_info[0]
        if request.get("use_url_shortener", True) and qr_code_data.startswith("http"):
            try:
                shortened = requests.get(
                    "https://is.gd/create.php?format=simple&url="
                    + urllib.parse.quote_plus(qr_code_data),
                    timeout=2.50,
                )
                if shortened.ok and shortened.text.startswith(
                    "http"
                ):  # make sure we got back a url
                    qr_code_data = shortened.text or qr_code_data
            except:  # Timeout, connection, etc.
                pass  # We can keep going without the shortened url and just use the original url
        qrcode_image = self.upload_qr_code(qr_code_data, size=(width, height))
        return qrcode_image, qr_code_data

    def upload_qr_code(self, qr_code_data: str, size=(DEFAULT_SIZE, DEFAULT_SIZE)):
        qr_size = min(size)
        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=11,
            border=9,
        )
        qr.add_data(qr_code_data)
        qr.make(fit=True)
        qrcode_image = qr.make_image(fill_color="black", back_color="white").convert(
            "RGB"
        )
        qrcode_image = qrcode_image.resize((qr_size, qr_size), Image.LANCZOS)
        qrcode_image = self.pad_image(qrcode_image, target_size=size)

        open_cv_image = np.array(qrcode_image)
        open_cv_image = open_cv_image[:, :, ::-1].copy()
        bytes = cv2.imencode(".png", open_cv_image)[1].tobytes()
        photo_url = upload_file_from_bytes(
            "cleaned_qr.png", bytes, content_type="image/png"
        )
        return photo_url

    def pad_image(
        self,
        pil_img: Image,
        target_size=(DEFAULT_SIZE, DEFAULT_SIZE),
        rgb=(255, 255, 255),
    ):
        width, height = pil_img.size
        left = (target_size[0] - width) // 2
        top = (target_size[1] - height) // 2
        result = Image.new(pil_img.mode, target_size, rgb)
        result.paste(pil_img, (left, top))
        return result

    def render_example(self, state: dict):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(
                f"""
                ```Prompt: {state.get("text_prompt", "")}```
                ```QR Content: {state.get("qr_code_data", "")}```
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
