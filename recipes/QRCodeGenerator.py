import typing


import qrcode
import numpy as np
import urllib
import cv2
import PIL.Image as Image
from daras_ai.image_input import upload_file_from_bytes

from furl import furl
from pydantic import BaseModel

import gooey_ui as st
from daras_ai_v2 import db
from daras_ai_v2.base import BasePage
from daras_ai_v2.img_model_settings_widgets import (
    guidance_scale_setting,
    model_selector,
    controlnet_settings,
)
from daras_ai_v2.descriptions import prompting101
from daras_ai_v2.stable_diffusion import (
    Text2ImgModels,
    controlnet,
    ControlNetModels,
    controlnet_model_explanations,
    text2img_model_ids,
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
        "num_inference_steps": 100,
        "guidance_scale": 9,
        "controlnet_conditioning_scale": [0.25, 0.45],
        "seed": 1331,
        "negative_prompt": "ugly, disfigured, low quality, blurry, nsfw, text, words",
        "use_image_input": False,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__.update(self.sane_defaults)

    class RequestModel(BaseModel):
        qr_code_input: str | None
        qr_code_input_image: str | None
        use_image_input: bool | None

        text_prompt: str | None
        negative_prompt: str | None

        selected_model: typing.Literal[tuple(e.name for e in Text2ImgModels)] | None
        selected_controlnet_model: typing.Tuple[
            typing.Literal[tuple(e.name for e in ControlNetModels)], ...
        ]

        size: int | None

        guidance_scale: float | None
        controlnet_conditioning_scale: typing.List[float]

        num_images: int | None
        num_inference_steps: int | None
        scheduler: str | None

        seed: int | None

    class ResponseModel(BaseModel):
        output_images: list[str]
        raw_images: list[str]

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
        if not st.session_state.get("use_image_input", False):
            st.text_area(
                """
                ### 🔗 URL
                Enter your URL, link or text. Generally shorter is better. We recommend using a URL shortener like bit.ly.
                """,
                key="qr_code_input",
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
        use_image_input = st.session_state.get("use_image_input", False)
        assert use_image_input or st.session_state.get(
            "qr_code_input"
        ), "Please provide QR Code URL or text content"
        assert not use_image_input or st.session_state.get(
            "qr_code_input_image"
        ), "You have checked the image upload option. Please upload a QR Code image"
        if use_image_input:
            req = urllib.request.urlopen(st.session_state.get("qr_code_input_image"))
            arr = np.asarray(bytearray(req.read()), dtype=np.uint8)
            img = cv2.imdecode(arr, -1)
            (
                retval,
                decoded_info,
                points,
                straight_qrcode,
            ) = cv2.QRCodeDetector().detectAndDecodeMulti(img)
            assert retval, "Please upload a valid QR Code image that is readable"

    def render_description(self):
        st.markdown(
            """
            Enter your URL (or text) and an image prompt and we'll generate an arty QR code with your artistic style and content in about 30 seconds. This is a rad way to advertise your website in IRL or print on a poster.
            It is made possible by the open source [Control Net](https://github.com/lllyasviel/ControlNet).
            """
        )
        prompting101()

    def render_steps(self):
        if not st.session_state.get("output_images"):
            st.markdown(
                """
                #### Generate the QR Code to see steps
                """
            )
            return
        # st.markdown(
        #     f"""
        #     #### Shorten the URL
        #     For more aesthetic and reliable QR codes with fewer black squares, we automatically shorten the URL: {"[INSERT SHORTENED URL HERE]"}
        #     """
        # )
        st.markdown(
            """
            #### Generate clean QR code
            Having consistent padding, formatting, and using high error correction in the QR Code encoding makes the QR code more readable and robust to damage and thus yields more reliable results with the model.
            """
        )
        imgs = st.session_state.get("image")
        if imgs:
            st.image(imgs[0])
        st.markdown(
            """
            #### Generate the QR Codes
            Use the model and controlnet constraints to generate QR codes that blend the prompt with the cleaned QR Code.
            """
        )
        for imgsrc in st.session_state.get("raw_images", []):
            st.image(imgsrc)
        st.markdown(
            """
            #### Run quality control
            We programatically scan the QR Codes to make sure they are readable and only use the working ones.
            """
        )
        for imgsrc in st.session_state["output_images"]:
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
        for img in state.get("output_images", []):
            st.image(img, caption=state.get("qr_code_input"))

    def run(self, state: dict) -> typing.Iterator[str | None]:
        for key, val in state.items():
            state[key] = tuple(val) if isinstance(val, list) else val

        request: QRCodeGeneratorPage.RequestModel = self.RequestModel.parse_obj(state)
        image, qr_code_input = self.preprocess_qr_code(request.dict())

        state["output_images"] = []

        selected_model = request.selected_model
        yield f"Running {Text2ImgModels[selected_model].value}..."

        state["raw_images"] = controlnet(
            selected_model=selected_model,
            selected_controlnet_models=request.selected_controlnet_model,
            prompt=request.text_prompt,
            num_outputs=2,
            init_image=image,
            num_inference_steps=request.num_inference_steps,
            negative_prompt=request.negative_prompt,
            guidance_scale=request.guidance_scale,
            seed=request.seed,
            controlnet_conditioning_scale=request.controlnet_conditioning_scale,
            scheduler=request.scheduler,
            selected_models_enum=Text2ImgModels,
            selected_models_ids=text2img_model_ids,
        )

        for src in state["raw_images"]:
            req = urllib.request.urlopen(src)
            arr = np.asarray(bytearray(req.read()), dtype=np.uint8)
            img = cv2.imdecode(arr, -1)
            (
                retval,
                decoded_info,
                points,
                straight_qrcode,
            ) = cv2.QRCodeDetector().detectAndDecodeMulti(img)
            if retval and decoded_info[0] == qr_code_input:
                state["output_images"].append(src)

        if len(state["output_images"]) == 0:  # TODO: generate safe qr code instead
            state["output_images"] = state["raw_images"]

    def preprocess_qr_code(self, request: dict):
        qr_code_input = request.get("qr_code_input")
        qr_code_input_image = request.get("qr_code_input_image")
        size = request.get("size", 512)
        if request.get("use_image_input", False):
            req = urllib.request.urlopen(qr_code_input_image)
            arr = np.asarray(bytearray(req.read()), dtype=np.uint8)
            img = cv2.imdecode(arr, -1)
            (
                retval,
                decoded_info,
                points,
                straight_qrcode,
            ) = cv2.QRCodeDetector().detectAndDecodeMulti(img)
            qr_code_input = decoded_info[0]
        qrcode_image = self.upload_qr_code(qr_code_input, size=size)
        image = [qrcode_image] * len(request.get("selected_controlnet_model", []))
        return image, qr_code_input

    @st.cache_data()
    def upload_qr_code(self, qr_code_input: str, size: int = 512):
        doc_ref = db.get_doc_ref(
            qr_code_input.replace("/", "_"), collection_id="qr_code_clean"
        )
        doc = db.get_or_create_doc(doc_ref).to_dict()
        photo_url = doc.get("photo_url" + str(size))
        if photo_url:
            return photo_url

        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=11,
            border=9,
        )
        qr.add_data(qr_code_input)
        qr.make(fit=True)
        qrcode_image = qr.make_image(fill_color="black", back_color="white").convert(
            "RGB"
        )
        qrcode_image = qrcode_image.resize((size, size), Image.LANCZOS)

        open_cv_image = np.array(qrcode_image)
        open_cv_image = open_cv_image[:, :, ::-1].copy()
        bytes = cv2.imencode(".png", open_cv_image)[1].tobytes()
        photo_url = upload_file_from_bytes(
            "cleaned_qr.png", bytes, content_type="image/png"
        )
        doc_ref.set({"photo_url" + str(size): photo_url})

        return photo_url

    def render_example(self, state: dict):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(
                f"""
                ```Prompt: {state.get("text_prompt", "")}```
                ```QR Content: {state.get("qr_code_input", "")}```
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
