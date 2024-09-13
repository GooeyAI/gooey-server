import typing
from enum import Enum

import numpy as np
from daras_ai_v2.pydantic_validation import FieldHttpUrl
import qrcode
import requests
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from furl import furl
from pydantic import BaseModel, Field
from pyzbar import pyzbar

import gooey_gui as gui
from app_users.models import AppUser
from bots.models import Workflow
from daras_ai.image_input import (
    upload_file_from_bytes,
    bytes_to_cv2_img,
    cv2_img_to_bytes,
)
from daras_ai_v2.base import BasePage
from daras_ai_v2.descriptions import prompting101
from daras_ai_v2.exceptions import raise_for_status, UserError
from daras_ai_v2.img_model_settings_widgets import (
    output_resolution_setting,
    img_model_settings,
)
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.repositioning import reposition_object, repositioning_preview_widget
from daras_ai_v2.safety_checker import safety_checker
from daras_ai_v2.stable_diffusion import (
    Text2ImgModels,
    controlnet,
    ControlNetModels,
    Img2ImgModels,
    Schedulers,
)
from daras_ai_v2.vcard import VCARD
from recipes.SocialLookupEmail import get_profile_for_email
from url_shortener.models import ShortenedURL
from daras_ai_v2.enum_selector_widget import enum_multiselect

ATTEMPTS = 1
DEFAULT_QR_CODE_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/a679a410-9456-11ee-bd77-02420a0001ce/QR%20Code.jpg.png"


class QrSources(Enum):
    qr_code_data = "🔗 URL or Text"
    qr_code_vcard = "📇 Contact Card"
    qr_code_file = "📄 Upload File"
    qr_code_input_image = "🏁 Existing QR Code"


class QRCodeGeneratorPage(BasePage):
    title = "AI Art QR Code"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/03d6538e-88d5-11ee-ad97-02420a00016c/W.I.2.png.png"
    workflow = Workflow.QR_CODE
    slug_versions = ["art-qr-code", "qr", "qr-code"]
    sdk_method_name = "qrCode"

    sane_defaults = dict(
        num_outputs=2,
        obj_scale=0.65,
        obj_pos_x=0.5,
        obj_pos_y=0.5,
        image_prompt_controlnet_models=[
            ControlNetModels.sd_controlnet_canny.name,
            ControlNetModels.sd_controlnet_depth.name,
            ControlNetModels.sd_controlnet_tile.name,
        ],
        image_prompt_strength=0.3,
        image_prompt_scale=1.0,
        image_prompt_pos_x=0.5,
        image_prompt_pos_y=0.5,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__.update(self.sane_defaults)

    class RequestModel(BasePage.RequestModel):
        qr_code_data: str | None
        qr_code_input_image: FieldHttpUrl | None
        qr_code_vcard: VCARD | None = Field(title="VCard")
        qr_code_file: FieldHttpUrl | None

        use_url_shortener: bool | None

        text_prompt: str
        negative_prompt: str | None
        image_prompt: str | None
        image_prompt_controlnet_models: list[ControlNetModels.api_enum] | None
        image_prompt_strength: float | None
        image_prompt_scale: float | None
        image_prompt_pos_x: float | None
        image_prompt_pos_y: float | None

        selected_model: typing.Literal[tuple(e.name for e in Text2ImgModels)] | None
        selected_controlnet_model: list[ControlNetModels.api_enum] | None

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
        output_images: list[FieldHttpUrl]
        raw_images: list[FieldHttpUrl]
        shortened_url: FieldHttpUrl | None
        cleaned_qr_code: FieldHttpUrl

    def preview_image(self, state: dict) -> str | None:
        if len(state.get("output_images") or []) > 0:
            return state["output_images"][0]
        return DEFAULT_QR_CODE_META_IMG

    def related_workflows(self) -> list:
        from recipes.CompareText2Img import CompareText2ImgPage
        from recipes.CompareUpscaler import CompareUpscalerPage
        from recipes.FaceInpainting import FaceInpaintingPage
        from recipes.EmailFaceInpainting import EmailFaceInpaintingPage

        return [
            CompareText2ImgPage,
            CompareUpscalerPage,
            FaceInpaintingPage,
            EmailFaceInpaintingPage,
        ]

    @classmethod
    def get_example_preferred_fields(cls, state: dict) -> list[str]:
        if state.get("qr_code_file"):
            return ["qr_code_file"]
        elif state.get("qr_code_input_image"):
            return ["qr_code_input_image"]
        else:
            return ["qr_code_data"]

    def render_form_v2(self):
        gui.text_area(
            """
            #### 👩‍💻 Prompt
            Describe the subject/scene of the QR Code.
            Choose clear prompts and distinguishable visuals to ensure optimal readability.
            """,
            key="text_prompt",
            placeholder="Bright sunshine coming through the cracks of a wet, cave wall of big rocks",
        )

        qr_code_source_key = "__qr_code_source"
        if qr_code_source_key not in gui.session_state:
            for key in QrSources._member_names_:
                if gui.session_state.get(key):
                    gui.session_state[qr_code_source_key] = key
                    break
        source = gui.horizontal_radio(
            "",
            options=QrSources._member_names_,
            key=qr_code_source_key,
            format_func=lambda s: QrSources[s].value,
        )

        _set_selected_qr_input_field(source)
        match source:
            case QrSources.qr_code_data.name:
                gui.text_area(
                    """
                    Enter your URL/Text below.
                    """,
                    key=QrSources.qr_code_data.name,
                    placeholder="https://www.gooey.ai",
                )

            case QrSources.qr_code_input_image.name:
                gui.file_uploader(
                    """
                    It will be reformatted and cleaned
                    """,
                    key=QrSources.qr_code_input_image.name,
                    accept=["image/*"],
                )

            case QrSources.qr_code_vcard.name:
                gui.caption(
                    "We'll use the prompt above to create a beautiful QR code that when scanned on a phone, will add the info below as a contact. Great for conferences and geeky parties."
                )
                vcard_form(key=QrSources.qr_code_vcard.name)

            case QrSources.qr_code_file.name:
                gui.file_uploader(
                    "Upload any file. Contact cards and PDFs work great.",
                    key=QrSources.qr_code_file.name,
                )

        if source != QrSources.qr_code_vcard:
            gui.checkbox(
                "🔗 Shorten URL",
                key="use_url_shortener",
            )
            gui.caption(
                'A shortened URL enables the QR code to be more beautiful and less "QR-codey" with fewer blocky pixels.'
            )

        gui.file_uploader(
            """
            #### 🏞️ Reference Image *[optional]*
            This image will be used as inspiration to blend with the QR Code.
            """,
            key="image_prompt",
            accept=["image/*"],
        )

    def validate_form_v2(self):
        assert gui.session_state.get("text_prompt"), "Please provide a prompt"
        assert any(
            gui.session_state.get(k) for k in QrSources._member_names_
        ), "Please provide QR Code URL, text content, contact info, or upload an image"

    def render_description(self):
        gui.markdown(
            """
            Create interactive and engaging QR codes with stunning visuals that are amazing for marketing, branding, and more. Combining AI Art and QR Code has never been easier! 
            Enter your URL and image prompt, and in just 30 seconds, we'll generate an artistic QR codes tailored to your style. 
            It is made possible by the open source [Control Net](https://github.com/lllyasviel/ControlNet).
            """
        )
        prompting101()

    def render_steps(self):
        email_import = gui.session_state.get("__email_imported")
        if email_import:
            gui.markdown("#### Import contact info from email")
            gui.json(email_import)
        shortened_url = gui.session_state.get("shortened_url")
        if shortened_url:
            gui.markdown(
                f"""
                #### Shorten the URL
                For more aesthetic and reliable QR codes with fewer black squares, we automatically shorten the URL: {shortened_url}
                """
            )
        img = gui.session_state.get("cleaned_qr_code")
        if img:
            gui.image(
                img,
                caption="""
                #### Generate clean QR code
                Having consistent padding, formatting, and using high error correction in the QR Code encoding makes the QR code more readable and robust to damage and thus yields more reliable results with the model.
                """,
            )
        raw_images = gui.session_state.get("raw_images", [])
        if raw_images:
            gui.markdown(
                """
#### Generate the QR Codes
We use the model and controlnet constraints to generate QR codes that blend the prompt with the cleaned QR Code. We generate them one at a time and check if they work. If they don't work, we try again. If they work, we stop.

Here are the attempts:
                """
            )
        for img in raw_images:
            gui.image(img)
        output_images = gui.session_state.get("output_images", [])
        if output_images:
            gui.markdown(
                """
#### Run quality control
We programatically scan the QR Codes to make sure they are readable. Once a working one is found, it becomes the output.

Here is the final output:
                """
            )
        for img in output_images:
            gui.image(img)

    def render_settings(self):
        gui.write(
            """
            Customize the QR Code output for your text prompt with these Settings. 
            """
        )

        img_model_settings(
            Img2ImgModels,
            show_scheduler=True,
            require_controlnet=True,
            extra_explanations={
                ControlNetModels.sd_controlnet_tile: "Tiling: Preserves more details of the QR Code, makes it more readable",
                ControlNetModels.sd_controlnet_brightness: "Brightness: Dictates how light the background of the QR Code will be. Contrast is desirable for readability",
            },
            controlnet_explanation="### 🎛️ Control Net\n[Control Net models](https://huggingface.co/lllyasviel?search=controlnet) provide a layer of refinement to the image generation process that blends with the QR code. Choose your preferred models: ",
            low_explanation="At {low} the prompted visual will be intact and the QR code will be more artistic but less readable",
            high_explanation="At {high} the control settings that blend the QR code will be applied tightly, possibly overriding the image prompt, but the QR code will be more readable",
        )
        gui.write("---")

        output_resolution_setting()

        gui.write(
            """
            ##### ⌖ QR Positioning
            Use this to control where the QR code is placed in the image, and how big it should be.
            """,
            className="gui-input",
        )
        col1, _ = gui.columns(2)
        with col1:
            obj_scale = gui.slider(
                "Scale",
                min_value=0.1,
                max_value=1.0,
                step=0.05,
                key="obj_scale",
            )
        col1, col2 = gui.columns(2, responsive=False)
        with col1:
            pos_x = gui.slider(
                "Position X",
                min_value=0.0,
                max_value=1.0,
                step=0.05,
                key="obj_pos_x",
            )
        with col2:
            pos_y = gui.slider(
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
                gui.session_state["output_width"],
                gui.session_state["output_height"],
            ),
            color=255,
        )

        if gui.session_state.get("image_prompt"):
            gui.write("---")
            gui.write(
                """
                ##### 🎨 Inspiration
                Use this to control how the image prompt should influence the output.
                """,
                className="gui-input",
            )
            gui.slider(
                "Inspiration Strength",
                min_value=0.0,
                max_value=1.0,
                step=0.05,
                key="image_prompt_strength",
            )
            enum_multiselect(
                ControlNetModels,
                label="Control Net Models",
                key="image_prompt_controlnet_models",
                checkboxes=False,
                allow_none=False,
            )
            gui.write(
                """
                ##### ⌖ Reference Image Positioning
                Use this to control where the reference image is placed, and how big it should be.
                """,
                className="gui-input",
            )
            col1, _ = gui.columns(2)
            with col1:
                image_prompt_scale = gui.slider(
                    "Scale",
                    min_value=0.1,
                    max_value=1.0,
                    step=0.05,
                    key="image_prompt_scale",
                )
            col1, col2 = gui.columns(2, responsive=False)
            with col1:
                image_prompt_pos_x = gui.slider(
                    "Position X",
                    min_value=0.0,
                    max_value=1.0,
                    step=0.05,
                    key="image_prompt_pos_x",
                )
            with col2:
                image_prompt_pos_y = gui.slider(
                    "Position Y",
                    min_value=0.0,
                    max_value=1.0,
                    step=0.05,
                    key="image_prompt_pos_y",
                )

            img_cv2 = mask_cv2 = bytes_to_cv2_img(
                requests.get(gui.session_state["image_prompt"]).content,
            )
            repositioning_preview_widget(
                img_cv2=img_cv2,
                mask_cv2=mask_cv2,
                obj_scale=image_prompt_scale,
                pos_x=image_prompt_pos_x,
                pos_y=image_prompt_pos_y,
                out_size=(
                    gui.session_state["output_width"],
                    gui.session_state["output_height"],
                ),
                color=255,
            )

    def render_output(self):
        state = gui.session_state
        self._render_outputs(state)

    def render_example(self, state: dict):
        self._render_outputs(state, max_count=1)

    def _render_outputs(self, state: dict, max_count: int | None = None):
        output_images = list(state.get("output_images", []))
        if max_count:
            output_images = output_images[:max_count]
        for img in output_images:
            gui.image(img, show_download_button=True)
            qr_code_data = (
                state.get(QrSources.qr_code_data.name)
                or state.get(QrSources.qr_code_input_image.name)
                or state.get(QrSources.qr_code_vcard.name, {}).get("format_name")
                or state.get(QrSources.qr_code_file.name)
            )
            if not qr_code_data:
                continue
            shortened_url = state.get("shortened_url")
            if not shortened_url:
                gui.caption(qr_code_data)
                continue
            hashid = furl(shortened_url.strip("/")).path.segments[-1]
            try:
                clicks = ShortenedURL.objects.get_by_hashid(hashid).clicks
            except ShortenedURL.DoesNotExist:
                clicks = None
            if clicks is not None:
                gui.caption(f"{shortened_url} → {qr_code_data} (Views: {clicks})")
            else:
                gui.caption(f"{shortened_url} → {qr_code_data}")

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: QRCodeGeneratorPage.RequestModel = self.RequestModel.parse_obj(state)

        yield "Running safety checker..."
        safety_checker(text=request.text_prompt, image=request.image_prompt)

        yield "Generating QR Code..."
        image, qr_code_data, did_shorten = generate_and_upload_qr_code(
            request, self.request.user
        )
        if did_shorten:
            state["shortened_url"] = qr_code_data
        state["cleaned_qr_code"] = image

        state["raw_images"] = raw_images = []

        yield f"Running {Text2ImgModels[request.selected_model].value}..."
        if isinstance(request.selected_controlnet_model, str):
            request.selected_controlnet_model = [request.selected_controlnet_model]
        init_images = [image] * len(request.selected_controlnet_model)
        if request.image_prompt:
            image_prompt = bytes_to_cv2_img(requests.get(request.image_prompt).content)
            repositioned_image_prompt, _ = reposition_object(
                orig_img=image_prompt,
                orig_mask=image_prompt,
                out_size=(request.output_width, request.output_height),
                out_obj_scale=request.image_prompt_scale,
                out_pos_x=request.image_prompt_pos_x,
                out_pos_y=request.image_prompt_pos_y,
                color=255,
            )
            request.image_prompt = upload_file_from_bytes(
                "repositioned_image_prompt.png",
                cv2_img_to_bytes(repositioned_image_prompt),
            )
            init_images += [request.image_prompt] * len(
                request.image_prompt_controlnet_models
            )
            request.selected_controlnet_model += request.image_prompt_controlnet_models
            request.controlnet_conditioning_scale += [
                request.image_prompt_strength
            ] * len(request.image_prompt_controlnet_models)
        state["output_images"] = controlnet(
            selected_model=request.selected_model,
            selected_controlnet_model=request.selected_controlnet_model,
            prompt=request.text_prompt,
            init_images=init_images,
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

    def preview_description(self, state: dict) -> str:
        return """
            Create interactive and engaging QR codes with stunning visuals that are amazing for marketing, branding, and more. Combining AI Art and QR Codes has never been easier! 
            Enter your URL and image prompt, and in just 30 seconds, we'll generate an artistic QR code tailored to your style. 
        """

    def get_raw_price(self, state: dict) -> int:
        selected_model = state.get("selected_model", Text2ImgModels.dream_shaper.name)
        total = 5
        match selected_model:
            case Text2ImgModels.deepfloyd_if.name:
                total += 3
            case Text2ImgModels.dall_e.name:
                total += 10
        return total * state.get("num_outputs", 1)

    def render_usage_guide(self):
        youtube_video("Q1D6B_-UoxY")


def vcard_form(*, key: str) -> VCARD:
    vcard_data = gui.session_state.get(key, {})
    # populate inputs
    for k in VCARD.__fields__.keys():
        gui.session_state.setdefault(f"__vcard_data__{k}", vcard_data.get(k) or "")
    vcard = VCARD.construct()

    vcard.email = gui.text_input(
        "Email", key="__vcard_data__email", placeholder="dev@gooey.ai"
    )

    if vcard.email and gui.button(
        "Import other contact info from my email - magic!",
        type="link",
    ):
        imported_vcard = get_vcard_from_email(vcard.email)
        if not imported_vcard or not imported_vcard.format_name:
            gui.error("No contact info found for that email")
        else:
            vcard = imported_vcard
            # update inputs
            for k, v in vcard.dict().items():
                gui.session_state[f"__vcard_data__{k}"] = v

    vcard.format_name = gui.text_input(
        "Name*",
        key="__vcard_data__format_name",
        placeholder="Supreme Overlord Alex Metzger, PhD",
    )
    vcard.tel = gui.text_input(
        "Phone Number",
        key="__vcard_data__tel",
        placeholder="+1 (420) 669-6969",
    )
    vcard.role = gui.text_input("Role", key="__vcard_data__role", placeholder="Intern")

    gui.session_state.setdefault("__vcard_data__urls_text", "\n".join(vcard.urls or []))
    vcard.urls = (
        gui.text_area(
            """
            Website Links  
            *([calend.ly](https://calend.ly) works great!)*
            """,
            placeholder="https://www.gooey.ai\nhttps://calend.ly/seanblagsvedt",
            key="__vcard_data__urls_text",
        )
        .strip()
        .splitlines()
    )

    vcard.photo_url = gui.text_input(
        "Photo URL",
        key="__vcard_data__photo_url",
        placeholder="https://www.gooey.ai/static/images/logo.png",
    )

    with gui.expander("More Contact Fields"):
        vcard.gender = gui.text_input(
            "Gender", key="__vcard_data__gender", placeholder="F"
        )
        vcard.note = gui.text_area(
            "Notes",
            key="__vcard_data__note",
            placeholder="- awesome person\n- loves pizza\n- plays tons of chess\n- absolutely a genius",
        )
        vcard.address = gui.text_area(
            "Address",
            key="__vcard_data__address",
            placeholder="123 Main gui, San Francisco, CA 94105",
        )

    gui.session_state[key] = vcard.dict()
    return vcard


def _set_selected_qr_input_field(
    selected: str, format_saved_key=lambda k: f"__saved_{k}"
):
    """
    There must be only one active QR-data input field at a time. The
    variables in state need to be set as per that. e.g. if qr_code_data
    is active, then other fields such as qr_code_input_image must be set
    to None.
    At the same time, we shouldn't lose data because a customer is
    trying out different modes on the UI.
    This helper method implements that by:
    - caching any previous form data from other fields with hidden keys
    - restoring previously saved data for this field
    """
    state = gui.session_state

    all_fields = QrSources._member_names_
    if selected not in all_fields:
        raise Exception(f"Invalid qr code input field: {selected}")

    # save all fields other than active_field
    for other in all_fields:
        if other != selected and state.get(other):
            state[format_saved_key(other)] = state[other]
            state.pop(other, None)

    # restore active field
    if not state.get(selected):
        try:
            state[selected] = state.pop(format_saved_key(selected))
        except KeyError:
            pass


def is_url(url: str) -> bool:
    try:
        URLValidator(schemes=["http", "https"])(url)
    except ValidationError:
        return False
    else:
        return True


def generate_and_upload_qr_code(
    request: QRCodeGeneratorPage.RequestModel,
    user: AppUser,
) -> tuple[str, str, bool]:
    if request.qr_code_vcard:
        vcf_str = request.qr_code_vcard.to_vcf_str()
        qr_code_data = ShortenedURL.objects.get_or_create_for_workflow(
            content=vcf_str,
            content_type="text/vcard",
            user=user,
            workflow=Workflow.QR_CODE,
        )[0].shortened_url()
        using_shortened_url = True
    else:
        if request.qr_code_file:
            qr_code_data = request.qr_code_file
        elif request.qr_code_input_image:
            qr_code_data = download_qr_code_data(request.qr_code_input_image)
        else:
            qr_code_data = request.qr_code_data
        if isinstance(qr_code_data, str):
            qr_code_data = qr_code_data.strip()
        if not qr_code_data:
            raise UserError("Please provide QR Code URL, text content, or an image")
        using_shortened_url = request.use_url_shortener
        if using_shortened_url:
            # only shorten valid urls
            using_shortened_url = is_url(qr_code_data)
            # prepend http:// to the URL if it has no scheme but is valid with http (similar to how browsers do it)
            if not using_shortened_url and is_url("http://" + qr_code_data):
                qr_code_data = "http://" + qr_code_data
                using_shortened_url = True
        if using_shortened_url:
            qr_code_data = ShortenedURL.objects.get_or_create_for_workflow(
                url=qr_code_data,
                user=user,
                workflow=Workflow.QR_CODE,
            )[0].shortened_url()

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
    return img_url, qr_code_data, using_shortened_url


def generate_qr_code(qr_code_data: str) -> np.ndarray:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, border=0)
    qr.add_data(qr_code_data)
    return np.array(qr.make_image().convert("RGB"))


def download_qr_code_data(url: str) -> str:
    r = requests.get(url)
    raise_for_status(r, is_user_url=True)
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


class InvalidQRCode(UserError):
    pass


def get_vcard_from_email(
    email: str, url_fields=("github_url", "linkedin_url", "facebook_url", "twitter_url")
) -> VCARD | None:
    person = get_profile_for_email(email)
    if not person:
        return None
    return VCARD(
        email=email,
        format_name=person.get("name") or "",
        tel=person.get("phone"),
        role=person.get("title"),
        # photo_url=photo_url,
        urls=list(set(filter(None, [person.get(field, "") for field in url_fields]))),
        note=person.get("headline"),
        organization=person.get("organization", {}).get("name"),
        address=", ".join(
            filter(
                None,
                [person.get("city"), person.get("state"), person.get("country")],
            )
        ),
    )
