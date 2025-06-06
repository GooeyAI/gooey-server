import re
import typing

import requests
from pydantic import BaseModel

import gooey_gui as gui
from bots.models import Workflow
from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2 import db, settings
from daras_ai_v2.base import BasePage
from daras_ai_v2.exceptions import raise_for_status
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.pydantic_validation import HttpUrlStr
from daras_ai_v2.stable_diffusion import InpaintingModels
from recipes.FaceInpainting import FaceInpaintingPage

email_regex = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
twitter_handle_regex = r"(@)?[A-Za-z0-9_]{1,15}"


class EmailFaceInpaintingPage(FaceInpaintingPage):
    title = "AI Generated Photo from Email Profile Lookup"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/ec0df5aa-9521-11ee-93d3-02420a0001e5/Email%20Profile%20Lookup.png.png"
    workflow = Workflow.EMAIL_FACE_INPAINTING
    slug_versions = ["EmailFaceInpainting", "ai-image-from-email-lookup"]

    sane_defaults = {
        "num_outputs": 1,
        "quality": 50,
        "output_width": 512,
        "output_height": 512,
        "guidance_scale": 7.5,
        "seed": 42,
        "upscale_factor": 1.0,
        "twitter_handle": "seanb",
    }

    class RequestModel(BasePage.RequestModel):
        email_address: str | None = None
        twitter_handle: str | None = None

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

        should_send_email: bool | None = None
        email_from: str | None = None
        email_cc: str | None = None
        email_bcc: str | None = None
        email_subject: str | None = None
        email_body: str | None = None
        email_body_enable_html: bool | None = None
        fallback_email_body: str | None = None

        seed: int | None = None

    class ResponseModel(BaseModel):
        input_image: HttpUrlStr
        resized_image: HttpUrlStr
        face_mask: HttpUrlStr
        diffusion_images: list[HttpUrlStr]
        output_images: list[HttpUrlStr]
        email_sent: bool = False

    @classmethod
    def get_example_preferred_fields(self, state: dict) -> list[str]:
        return ["email_address"]

    def render_description(self):
        gui.write(
            """
    *EmailID > Profile pic > Face Masking + Zoom > Stable Diffusion > GFPGAN > Email*  
    
    This recipe takes only an email address and returns a photo of the person with that email, rendered using the text prompt.
    
    How It Works:
    
    1. Calls social media APIs to get a user's twitter, facebook, linkedin or insta profile photo 
    2. Extracts faces from any image
    3. Adjusts the zoom and X & Y placement of the face
    4. Generates images from the given prompt and inpaints with Stable diffusion
    5. Improves faces using gfpgan   
    6. Sends an email with the rendered image
    """
        )

    def render_form_v2(self):
        gui.text_area(
            """
            #### Prompt
            Describe the scene that you'd like to generate around the face. 
            """,
            key="text_prompt",
            placeholder="winter's day in paris",
        )
        if "__photo_source" not in gui.session_state:
            gui.session_state["__photo_source"] = (
                "Email Address"
                if gui.session_state.get("email_address")
                else "Twitter Handle"
            )

        source = gui.radio(
            """
            #### Photo Source
            From where we should get the photo?""",
            options=["Email Address", "Twitter Handle"],
            key="__photo_source",
        )
        if source == "Email Address":
            gui.text_input(
                """
                #### Email Address
                Give us your email address and we'll try to get your photo 
                """,
                key="email_address",
                placeholder="john@appleseed.com",
            )
            gui.session_state["twitter_handle"] = None
        else:
            gui.text_input(
                """
                #### Twitter Handle
                Give us your twitter handle, we'll try to get your photo from there
                """,
                key="twitter_handle",
                max_chars=15,
            )
            gui.session_state["email_address"] = None

    def validate_form_v2(self):
        text_prompt = gui.session_state.get("text_prompt")
        email_address = gui.session_state.get("email_address")
        twitter_handle = gui.session_state.get("twitter_handle")
        assert text_prompt, "Please provide a Prompt and your Email Address"

        if gui.session_state.get("twitter_handle"):
            assert re.fullmatch(twitter_handle_regex, twitter_handle), (
                "Please provide a valid Twitter Handle"
            )
        elif gui.session_state.get("email_address"):
            assert re.fullmatch(email_regex, email_address), (
                "Please provide a valid Email Address"
            )
        else:
            raise AssertionError("Please provide an Email Address or Twitter Handle")

        from_email = gui.session_state.get("email_from")
        email_subject = gui.session_state.get("email_subject")
        email_body = gui.session_state.get("email_body")
        assert from_email and email_subject and email_body, (
            "Please provide a From Email, Subject & Body"
        )

    def related_workflows(self) -> list:
        from recipes.FaceInpainting import FaceInpaintingPage
        from recipes.SocialLookupEmail import SocialLookupEmailPage
        from recipes.SEOSummary import SEOSummaryPage
        from recipes.LipsyncTTS import LipsyncTTSPage

        return [
            FaceInpaintingPage,
            SocialLookupEmailPage,
            SEOSummaryPage,
            LipsyncTTSPage,
        ]

    def render_usage_guide(self):
        youtube_video("3C23HwQPITg")

    # def render_settings(self):
    #     super().render_settings()
    #     gui.write(
    #         """
    #         ### Email settings
    #         """
    #     )
    #
    #     gui.checkbox(
    #         "Send email",
    #         key="should_send_email",
    #     )
    #     gui.text_input(
    #         label="From",
    #         key="email_from",
    #     )
    #     gui.text_input(
    #         label="Cc (You can enter multiple emails separated by comma)",
    #         key="email_cc",
    #         placeholder="john@gmail.com, cathy@gmail.com",
    #     )
    #     gui.text_input(
    #         label="Bcc (You can enter multiple emails separated by comma)",
    #         key="email_bcc",
    #         placeholder="john@gmail.com, cathy@gmail.com",
    #     )
    #     gui.text_input(
    #         label="Subject",
    #         key="email_subject",
    #     )
    #     gui.checkbox(
    #         label="Enable HTML Body",
    #         key="email_body_enable_html",
    #     )
    #     gui.text_area(
    #         label="Body (use {{output_images}} to insert the images into the email)",
    #         key="email_body",
    #     )
    #     gui.text_area(
    #         label="Fallback Body (in case of failure)",
    #         key="fallback_email_body",
    #     )
    #
    # def render_output(self):
    #     super().render_output()
    #
    #     if gui.session_state.get("email_sent"):
    #         gui.write(f"✅ Email sent to {gui.session_state.get('email_address')}")
    #     else:
    #         gui.div()

    def run(self, state: dict):
        request: EmailFaceInpaintingPage.RequestModel = (
            self.RequestModel.model_validate(state)
        )

        yield "Fetching profile..."
        photo_url = self._get_photo_url(request)
        if photo_url:
            state["input_image"] = photo_url
            yield from super().run(state)

        # output_images = state.get("output_images")
        #
        # if request.should_send_email and (output_images or request.fallback_email_body):
        #     yield "Sending Email..."
        #
        #     send_email_via_postmark(
        #         from_address=request.email_from,
        #         to_address=request.email_address,
        #         cc=request.email_cc,
        #         bcc=request.email_bcc,
        #         subject=request.email_subject,
        #         html_body=self._get_email_body(request, output_images),
        #         message_stream="gooey-ai-workflows",
        #     )
        #     state["email_sent"] = True

        if not photo_url:
            raise ImageNotFound(
                "This email has no photo with a face in it. Try [Face in an AI Image](/face-in-ai-generated-photo/) workflow instead."
            )

    def _get_photo_url(self, request):
        if request.email_address:
            photo_url = get_photo_for_email(request.email_address)
        else:
            # For twitter-photo-cache to find the user irrespective
            # User may enter the handle case-insensitively
            clean_handle = self._clean_handle(request.twitter_handle)
            photo_url = get_photo_for_twitter_handle(clean_handle)
        return photo_url

    def _clean_handle(self, twitter_handle: str) -> str:
        without_at_sign = twitter_handle.replace("@", "")
        lower_case_handle = without_at_sign.lower()
        return lower_case_handle

    def _get_email_body(
        self,
        request: "EmailFaceInpaintingPage.RequestModel",
        output_images: [str],
    ) -> str:
        if output_images:
            # convert images to html
            output_images_html = ""
            for img_url in output_images:
                output_images_html += f'<img width="300px" src="{img_url}"/>'

            # remove `{{output_images}}` placeholder
            parts = request.email_body.split("{{output_images}}")

            # if not html, wrap in a div to render as text
            if not request.email_body_enable_html:
                parts = [
                    f'<div style="white-space: pre-wrap;">{part}</div>'
                    for part in parts
                ]

            # add output images as html
            email_body = output_images_html.join(parts)

        else:
            # no output images, use fallback
            email_body = request.fallback_email_body

            # if not html, wrap in a div to render as text
            if not request.email_body_enable_html:
                email_body = f'<div style="white-space: pre-wrap;">{email_body}</div>'

        return email_body

    def render_run_preview_output(self, state: dict):
        if state.get("email_address"):
            gui.write("**Input Email** -", state.get("email_address"))
        elif state.get("twitter_handle"):
            gui.write("**Input Twitter Handle** -", state.get("twitter_handle"))
        output_images = state.get("output_images")
        if output_images:
            for img in output_images:
                gui.image(
                    img,
                    caption="```"
                    + state.get("text_prompt", "").replace("\n", "")
                    + "```",
                )


class ImageNotFound(Exception):
    "Raised when the image not found in email profile"

    pass


class TwitterError(Exception):
    "Raised when the twitter handle Lookup returns an error"

    pass


def get_photo_for_email(email_address):
    doc_ref = db.get_doc_ref(email_address, collection_id="apollo_io_photo_cache")

    doc = db.get_or_create_doc(doc_ref).to_dict()
    photo_url = doc.get("photo_url")
    if photo_url:
        return photo_url


def get_photo_for_twitter_handle(twitter_handle):
    import glom

    doc_ref = db.get_doc_ref(twitter_handle, collection_id="twitter_photo_cache")

    doc = db.get_or_create_doc(doc_ref).to_dict()
    photo_url = doc.get("photo_url")
    if photo_url:
        return photo_url
    r = requests.get(
        f"https://api.twitter.com/2/users/by?usernames={twitter_handle}&user.fields=profile_image_url",
        headers={"Authorization": f"Bearer {settings.TWITTER_BEARER_TOKEN}"},
    )
    raise_for_status(r)
    error = glom.glom(r.json(), "errors.0.title", default=None)
    if error:
        if error == "Not Found Error":
            raise TwitterError("Twitter handle does not exist")
        raise TwitterError(error)

    twitter_photo_url_normal = glom.glom(
        r.json(), "data.0.profile_image_url", default=None
    )
    if twitter_photo_url_normal:
        original_photo_url = twitter_photo_url_normal.replace("_normal", "")
        photo_url = upload_file_from_bytes(
            "face_photo.png", requests.get(original_photo_url).content
        )
        doc_ref.set({"photo_url": photo_url})
        return photo_url
