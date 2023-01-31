import re
import typing

import requests
import streamlit as st
from pydantic import BaseModel

from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2 import db
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.send_email import send_email_via_postmark
from daras_ai_v2.stable_diffusion import InpaintingModels
from recipes.FaceInpainting import FaceInpaintingPage

email_regex = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"


class EmailFaceInpaintingPage(FaceInpaintingPage):
    title = "AI Generated Photo from Email Profile Lookup"
    slug_versions = ["EmailFaceInpainting", "ai-image-from-email-lookup"]
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
        email_address: str

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

        should_send_email: bool | None
        email_from: str | None
        email_cc: str | None
        email_bcc: str | None
        email_subject: str | None
        email_body: str | None
        email_body_enable_html: bool | None
        fallback_email_body: str | None

        seed: int | None

        class Config:
            schema_extra = {
                "example": {
                    "text_prompt": "winter's day in paris",
                    "email_address": "sean@dara.network",
                }
            }

    class ResponseModel(BaseModel):
        input_image: str
        resized_image: str
        face_mask: str
        diffusion_images: list[str]
        output_images: list[str]
        email_sent: bool = False

    def preview_description(self, state: dict) -> str:
        return "Find an email's public photo and then draw the face into an AI generated scene using your own prompt + the latest Stable Diffusion or DallE image generator."

    def render_description(self):
        st.write(
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
        st.text_area(
            """
            ### Prompt
            Describe the scene that you'd like to generate around the face. 
            """,
            key="text_prompt",
            placeholder="winter's day in paris",
        )

        st.text_input(
            """
            ### Email Address
            Give us your email address and we'll try to get your photo 
            """,
            key="email_address",
            placeholder="john@appleseed.com",
        )

    def validate_form_v2(self):
        text_prompt = st.session_state.get("text_prompt")
        email_address = st.session_state.get("email_address")
        assert (
            text_prompt and email_address
        ), "Please provide a Prompt and your Email Address"

        assert re.fullmatch(
            email_regex, email_address
        ), "Please provide a valid Email Address"

        from_email = st.session_state.get("email_from")
        email_subject = st.session_state.get("email_subject")
        email_body = st.session_state.get("email_body")
        assert (
            from_email and email_subject and email_body
        ), "Please provide a From Email, Subject & Body"

    def render_settings(self):
        super().render_settings()
        st.write(
            """
            ### Email settings
            """
        )

        st.checkbox(
            "Send email",
            key="should_send_email",
        )
        st.text_input(
            label="From",
            key="email_from",
        )
        st.text_input(
            label="Cc (You can enter multiple emails separated by comma)",
            key="email_cc",
            placeholder="john@gmail.com, cathy@gmail.com",
        )
        st.text_input(
            label="Bcc (You can enter multiple emails separated by comma)",
            key="email_bcc",
            placeholder="john@gmail.com, cathy@gmail.com",
        )
        st.text_input(
            label="Subject",
            key="email_subject",
        )
        st.checkbox(
            label="Enable HTML Body",
            key="email_body_enable_html",
        )
        st.text_area(
            label="Body (use {{output_images}} to insert the images into the email)",
            key="email_body",
        )
        st.text_area(
            label="Fallback Body (in case of failure)",
            key="fallback_email_body",
        )

    def render_output(self):
        super().render_output()

        if st.session_state.get("email_sent"):
            st.write(f"✅ Email sent to {st.session_state.get('email_address')}")
        else:
            st.empty()

    def run(self, state: dict):
        request: EmailFaceInpaintingPage.RequestModel = self.RequestModel.parse_obj(
            state
        )

        yield "Fetching profile..."

        photo_url = get_photo_for_email(request.email_address)
        if photo_url:
            state["input_image"] = photo_url
            yield from super().run(state)

        output_images = state.get("output_images")

        if request.should_send_email and (output_images or request.fallback_email_body):
            yield "Sending Email..."

            send_email_via_postmark(
                from_address=request.email_from,
                to_address=request.email_address,
                cc=request.email_cc,
                bcc=request.email_bcc,
                subject=request.email_subject,
                html_body=self._get_email_body(request, output_images),
            )
            state["email_sent"] = True

        if not photo_url:
            raise ValueError("Photo not found")

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

    def render_example(self, state: dict):
        st.write("**Input Email** -", state.get("email_address"))
        output_images = state.get("output_images")
        if output_images:
            for img in output_images:
                st.image(
                    img,
                    caption="```"
                    + state.get("text_prompt", "").replace("\n", "")
                    + "```",
                )

    def render_usage_guide(self):
        youtube_video("bffH8X3YBCQ")


@st.cache()
def get_photo_for_email(email_address):
    state = db.get_or_create_doc(
        db.get_doc_ref(email_address, collection_id="apollo_io_photo_cache")
    ).to_dict()

    photo_url = state.get("photo_url")
    if photo_url:
        return photo_url

    r = requests.post(
        "https://api.apollo.io/v1/people/match",
        json={
            "api_key": "BOlC1SGQWNuP3D70WA_-yw",
            "email": email_address,
        },
    )
    r.raise_for_status()

    photo_url = r.json()["person"]["photo_url"]
    if not photo_url:
        return

    photo_url = upload_file_from_bytes(
        "face_photo.png",
        requests.get(photo_url).content,
        content_type="image/png",
    )

    db.get_doc_ref(
        email_address,
        collection_id="apollo_io_photo_cache",
    ).set({"photo_url": photo_url})

    return photo_url


if __name__ == "__main__":
    EmailFaceInpaintingPage().render()
