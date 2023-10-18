import typing
import time

import numpy as np
import qrcode
import requests
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from furl import furl
from pydantic import BaseModel
from pyzbar import pyzbar

import gooey_ui as st
from app_users.models import AppUser
from bots.models import Workflow
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
from url_shortener.models import ShortenedURL
from daras_ai_v2.loom_video_widget import youtube_video

ATTEMPTS = 1
DEFAULT_QR_CODE_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/f09c8cfa-5393-11ee-a837-02420a000190/ai%20art%20qr%20codes1%201.png.png"


class QRCodeGeneratorPage(BasePage):
    title = "AI Art QR Code"
    workflow = Workflow.QR_CODE
    slug_versions = ["art-qr-code", "qr", "qr-code"]

    sane_defaults = dict(
        num_outputs=2,
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

        vcard_data: dict | None

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

    def preview_image(self, state: dict) -> str | None:
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

    def render_form_v2(self):
        st.text_area(
            """
            ### 👩‍💻 Prompt
            Describe the subject/scene of the QR Code.
            Choose clear prompts and distinguishable visuals to ensure optimal readability.
            """,
            key="text_prompt",
            placeholder="Bright sunshine coming through the cracks of a wet, cave wall of big rocks",
        )

        VCARD_CAPTION = "Save some trees with the coolest reusable business card ever (get it printed on metal for ultimate wow factor)! 🌳 These special vCard QR codes can contain your contact information and will automatically enter them into the contacts of whoever scans them!"
        st.session_state.setdefault(
            "__use_vcard", bool(st.session_state.get("vcard_data"))
        )
        if st.checkbox("📇 vCard", key="__use_vcard"):
            st.caption(VCARD_CAPTION)
            fields = st.session_state.get("vcard_data", {})
            for field in fields:
                st.session_state["__" + field] = fields.get(field, None)
            fields = {}
            fields["format_name"] = st.text_input(
                "Name",
                key="__format_name",
                placeholder="Supreme Overlord Alex Metzger, PhD",
            )
            with st.expander("Optional Fields"):
                fields["email"] = st.text_input(
                    "Email", key="__email", placeholder="example@gmail.com"
                )
                fields["gender"] = st.text_input(
                    "Gender", key="__gender", placeholder="F"
                )
                fields["birthday_year"] = st.text_input(
                    "Birthday Year", key="__birthday_year", placeholder="1990"
                )
                fields["birthday_month"] = st.text_input(
                    "Birthday Month", key="__birthday_month", placeholder="01"
                )
                fields["birthday_day"] = st.text_input(
                    "Birthday Day", key="__birthday_day", placeholder="01"
                )
                fields["family_name"] = st.text_input(
                    "Family Name", key="__family_name", placeholder="Metzger"
                )
                fields["given_name"] = st.text_input(
                    "Given Name", key="__given_name", placeholder="Alexander"
                )
                fields["middle_names"] = st.text_input(
                    "Additional/Middle Names", key="__middle_names", placeholder="Le"
                )
                fields["honorific_prefixes"] = st.text_input(
                    "Honorific Prefixes",
                    key="__honorific_prefixes",
                    placeholder="Supreme, Overlord",
                )
                fields["honorific_suffixes"] = st.text_input(
                    "Honorific Suffixes", key="__honorific_suffixes", placeholder="PhD"
                )
                fields["impp"] = st.text_input(
                    "Instant Messenger Handle",
                    key="__impp",
                    placeholder="aim:johndoe@aol.com",
                )
                fields["address"] = st.text_input(
                    "Address",
                    key="__address",
                    placeholder="123 Main St, San Francisco, CA 94105",
                )
                fields["calendar_url"] = st.text_input(
                    "Calendar URL",
                    key="__calendar_url",
                    placeholder="https://calendar.google.com/calendar/u/0/r",
                )
                fields["comma_separated_categories"] = st.text_input(
                    "Keywords",
                    key="__comma_separated_categories",
                    placeholder="tennis player, software engineer",
                )
                fields["kind"] = st.radio(
                    "Kind",
                    key="__kind",
                    options=[
                        "individual",
                        "application",
                        "group",
                        "location",
                        "organization",
                    ],
                )
                fields["language"] = st.text_input(
                    "Language", key="__language", placeholder="en-US"
                )
                fields["organization"] = st.text_input(
                    "Organization", key="__organization", placeholder="Gooey.AI"
                )
                fields["photo_url"] = st.file_uploader(
                    "Photo", key="__photo_url", accept=["image/*"]
                )
                fields["logo_url"] = st.file_uploader(
                    "Logo", key="__logo_url", accept=["image/*"]
                )
                fields["role"] = st.text_input(
                    "Role", key="__role", placeholder="Intern"
                )
                fields["timezone"] = st.text_input(
                    "Timezone", key="__timezone", placeholder="America/Los_Angeles"
                )
                fields["job_title"] = st.text_input(
                    "Job Title", key="__job_title", placeholder="Supreme Overlord"
                )
                st.session_state["__urls"] = "\n".join(
                    st.session_state.get("__urls", [])
                )
                fields["urls"] = st.text_area(
                    "URLs",
                    key="__urls",
                    placeholder="https://www.gooey.ai\nhttps://farmer.chat",
                ).split("\n")
                fields["tel"] = st.text_input(
                    "Phone Number", key="__tel", placeholder="+1 (420) 669-6969"
                )
            st.session_state["vcard_data"] = fields
        else:
            st.caption(VCARD_CAPTION)
            st.session_state["vcard_data"] = None
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
                    Enter your URL below. Shorter links give more visually appealing results. 
                    """,
                    key="qr_code_data",
                    placeholder="https://www.gooey.ai",
                )
            st.session_state["qr_code_input_image"] = None
            st.checkbox("🔗 Shorten URL", key="use_url_shortener")
            st.caption(
                'A shortened URL enables the QR code to be more beautiful and less "QR-codey" with fewer blocky pixels.'
            )

    def validate_form_v2(self):
        assert st.session_state["text_prompt"], "Please provide a prompt"

        if st.session_state["vcard_data"]:
            assert st.session_state["vcard_data"][
                "format_name"
            ], "Please provide a name"
            return

        qr_code_data = st.session_state.get("qr_code_data")
        qr_code_input_image = st.session_state.get("qr_code_input_image")
        assert (
            qr_code_data or qr_code_input_image
        ), "Please provide QR Code URL, text content, or upload an image"

    def render_description(self):
        st.markdown(
            """
            Create interactive and engaging QR codes with stunning visuals that are amazing for marketing, branding, and more. Combining AI Art and QR Code has never been easier! 
            Enter your URL and image prompt, and in just 30 seconds, we'll generate an artistic QR codes tailored to your style. 
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

    def _render_outputs(self, state: dict):
        for img in state.get("output_images", []):
            st.image(img)
            qr_code_data = state.get("qr_code_data")
            if not qr_code_data:
                continue
            shortened_url = state.get("shortened_url")
            if not shortened_url:
                st.caption(qr_code_data)
                continue
            hashid = furl(shortened_url.strip("/")).path.segments[-1]
            try:
                clicks = ShortenedURL.objects.get_by_hashid(hashid).clicks
            except ShortenedURL.DoesNotExist:
                clicks = None
            if clicks is not None:
                st.caption(f"{shortened_url} → {qr_code_data} (Views: {clicks})")
            else:
                st.caption(f"{shortened_url} → {qr_code_data}")

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: QRCodeGeneratorPage.RequestModel = self.RequestModel.parse_obj(state)

        if request.vcard_data:
            yield "Saving vCard..."
            plain_text = format_vcard_string(**request.vcard_data)
            request.qr_code_data = upload_file_from_bytes(
                "vCard.vcf", plain_text.encode(), "text/vcard"
            )
            request.use_url_shortener = True
            request.qr_code_input_image = None

        yield "Generating QR Code..."
        image, qr_code_data, did_shorten = generate_and_upload_qr_code(
            request, self.request.user
        )
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
    qr_code_data = request.qr_code_data
    if request.qr_code_input_image:
        qr_code_data = download_qr_code_data(request.qr_code_input_image)

    if isinstance(qr_code_data, str):
        qr_code_data = qr_code_data.strip()
    if not qr_code_data:
        raise ValueError("Please provide QR Code URL, text content, or an image")

    shortened = request.use_url_shortener and is_url(qr_code_data)
    if shortened:
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
    return img_url, qr_code_data, shortened


def generate_qr_code(qr_code_data: str) -> np.ndarray:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, border=0)
    qr.add_data(qr_code_data)
    return np.array(qr.make_image().convert("RGB"))


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


def format_vcard_string(
    *,
    format_name: str,
    email: str | None = None,
    gender: str | None = None,
    birthday_year: str | None = None,
    birthday_month: str | None = None,
    birthday_day: str | None = None,
    family_name: str | None = None,
    given_name: str | None = None,
    middle_names: str | None = None,
    honorific_prefixes: str | None = None,
    honorific_suffixes: str | None = None,
    impp: str | None = None,
    address: str | None = None,
    calendar_url: str | None = None,
    comma_separated_categories: str | None = None,
    kind: str | None = None,
    language: str | None = None,
    organization: str | None = None,
    photo_url: str | None = None,
    logo_url: str | None = None,
    role: str | None = None,
    timezone: str | None = None,
    job_title: str | None = None,
    urls: list[str] = [],
    tel: str | None = None,
) -> str:
    vcard_string = "BEGIN:VCARD\nVERSION:4.0\n"
    if format_name:
        vcard_string += f"FN:{format_for_vcard(format_name)}\n"
    else:
        raise ValueError("Please provide a name")
    if email:
        vcard_string += f"EMAIL:{format_for_vcard(email)}\n"
    if gender:
        vcard_string += f"GENDER:{format_for_vcard(gender)}\n"
    if birthday_year or birthday_month or birthday_day:
        vcard_string += f'BDAY:{format_for_vcard((birthday_year or "--") + (birthday_month or "--").rjust(2, "0") + (birthday_day  or "--").rjust(2, "0"))}\n'
    if (
        family_name
        or given_name
        or middle_names
        or honorific_prefixes
        or honorific_suffixes
    ):
        vcard_string += f'N:{format_for_vcard(family_name or "")};{format_for_vcard(given_name or "")};{format_for_vcard(middle_names or "")};{format_for_vcard(honorific_prefixes or "")};{format_for_vcard(honorific_suffixes or "")}\n'
    if impp:
        vcard_string += f"IMPP:{format_for_vcard(impp)}\n"
    if address:
        vcard_string += f"ADR:{format_for_vcard(address)}\n"
    if calendar_url:
        vcard_string += f"CALURI:{format_for_vcard(calendar_url)}\n"
    if comma_separated_categories:
        vcard_string += f"CATEGORIES:{format_for_vcard(comma_separated_categories)}\n"
    if kind:
        vcard_string += f"KIND:{format_for_vcard(kind)}\n"
    if language:
        vcard_string += f"LANG:{format_for_vcard(language)}\n"
    if organization:
        vcard_string += f"ORG:{format_for_vcard(organization)}\n"
    if photo_url:
        vcard_string += f"PHOTO;MEDIATYPE=image/jpeg:{format_for_vcard(photo_url)}\n"
    if logo_url:
        vcard_string += f"LOGO;MEDIATYPE=image/jpeg:{format_for_vcard(logo_url)}\n"
    if role:
        vcard_string += f"ROLE:{format_for_vcard(role)}\n"
    if timezone:
        vcard_string += f"TZ:{format_for_vcard(timezone)}\n"
    if job_title:
        vcard_string += f"TITLE:{format_for_vcard(job_title)}\n"
    if urls:
        for url in urls:
            vcard_string += f"URL:{format_for_vcard(url)}\n"
    if tel:
        vcard_string += f"TEL;TYPE=cell:{format_for_vcard(tel)}\n"
    return (
        vcard_string
        + f"REV:{str(time.time()).strip('.')}\nPRODID:-//GooeyAI//NONSGML Gooey vCard V1.0//EN\nEND:VCARD"
    )


def format_for_vcard(vcard_string: str) -> str:
    vcard_string = vcard_string.replace("\n", "\\n").replace(";", "\\;")
    if len(vcard_string) > 75:
        vcard_string = "\n ".join(
            vcard_string[i : i + 74] for i in range(0, len(vcard_string), 74)
        )
    return vcard_string
