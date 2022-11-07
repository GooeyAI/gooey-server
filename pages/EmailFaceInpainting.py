import re

import requests
import streamlit as st
from pydantic import BaseModel

from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.base import get_saved_doc, set_saved_doc, get_doc_ref
from daras_ai_v2.send_email import send_email_via_postmark
from pages.FaceInpainting import FaceInpaintingPage

email_regex = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"


class EmailFaceInpaintingPage(FaceInpaintingPage):
    title = "Email of You In Any Scene"
    doc_name = "EmailFaceInpainting#2"
    endpoint = "/v1/EmailFaceInpainting/run"

    class RequestModel(BaseModel):
        email_address: str
        text_prompt: str = None

        num_outputs: int = None
        quality: int = None

        should_send_email: bool = None
        email_from: str = None
        email_cc: str = None
        email_bcc: str = None
        email_subject: str = None
        email_body: str = None
        email_body_enable_html: bool = None
        fallback_email_body: str = None

        face_scale: float = None
        face_pos_x: float = None
        face_pos_y: float = None

        output_width: int = None
        output_height: int = None

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

    def render_form(self):
        with st.form("my_form"):
            st.write(
                """
                ### Prompt
                Describe the scene that you'd like to generate around the face. 
                """
            )
            st.text_input(
                "text_prompt",
                label_visibility="collapsed",
                key="text_prompt",
                placeholder="winter's day in paris",
            )

            st.write(
                """
                ### Email Address
                Give us your email address and we'll try to get your photo 
                """
            )
            st.text_input(
                "email_address",
                label_visibility="collapsed",
                key="email_address",
                placeholder="john@appleseed.com",
            )
            st.caption(
                "By providing your email address, you agree to Gooey.AI's [Privacy Policy](https://dara.network/privacy)"
            )

            col1, col2 = st.columns(2, gap="medium")
            with col1:
                st.slider(
                    label="# of Outputs",
                    key="num_outputs",
                    min_value=1,
                    max_value=4,
                )
            with col2:
                st.slider(
                    label="Quality",
                    key="num_steps",
                    min_value=10,
                    max_value=100,
                    step=10,
                )

            submitted = st.form_submit_button("🏃‍ Submit")

        if submitted:
            text_prompt = st.session_state.get("text_prompt")
            email_address = st.session_state.get("email_address")
            if not (text_prompt and email_address):
                st.error("Please provide a Prompt and your Email Address", icon="⚠️")
                return False

            if not re.fullmatch(email_regex, email_address):
                st.error("Please provide a valid Email Address", icon="⚠️")
                return False

            from_email = st.session_state.get("email_from")
            email_subject = st.session_state.get("email_subject")
            email_body = st.session_state.get("email_body")
            if not (from_email and email_subject and email_body):
                st.error("Please provide a From Email, Subject & Body")
                return False

        return submitted

    def render_settings(self):
        super().render_settings()
        st.write(
            """
            ### Email settings
            """
        )

        st.checkbox(
            "Should Send email",
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
        st.write("Input Email -", state.get("email_address"))
        super().render_example(state)


@st.cache()
def get_photo_for_email(email_address):
    state = get_saved_doc(
        get_doc_ref(email_address, collection_id="apollo_io_photo_cache")
    )
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
        "face_photo.png", requests.get(photo_url).content
    )
    set_saved_doc(
        get_doc_ref(email_address, collection_id="apollo_io_photo_cache"),
        {"photo_url": photo_url},
    )

    return photo_url


if __name__ == "__main__":
    EmailFaceInpaintingPage().render()
