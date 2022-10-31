import re
from copy import deepcopy

import requests
import streamlit as st
from pydantic import BaseModel

from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.base import get_saved_doc, set_saved_doc, get_doc_ref
from daras_ai_v2.send_email import send_smtp_message
from pages.FaceInpainting import FaceInpaintingPage


email_regex = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"


class EmailFaceInpaintingPage(FaceInpaintingPage):
    title = "Email of You In Any Scene"
    doc_name = "EmailFaceInpainting#2"
    endpoint = "/v1/EmailFaceInpainting/run"

    class RequestModel(BaseModel):
        email_address: str
        text_prompt: str

        num_outputs: int = None
        quality: int = None
        email_from: str = None
        email_cc: str = None
        email_subject: str = None
        email_body: str = None
        should_send_email: bool = None

        face_scale: float = None
        face_pos_x: float = None
        face_pos_y: float = None

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
        email_sent: bool

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

        return submitted

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
            label="From email",
            key="email_from",
        )
        st.text_input(
            label="CC emails (You can enter multiple emails separated by comma)",
            key="email_cc",
            placeholder="john@gmail.com, cathy@gmail.com",
        )
        st.text_input(
            label="Subject",
            key="email_subject",
        )
        st.text_area(
            label="Body",
            key="email_body",
        )

    def render_output(self):
        super().render_output()

        if st.session_state.get("email_sent"):
            st.write(f"✅ Email sent to {st.session_state.get('email_address')}")
        else:
            st.empty()

    def run(self, state: dict):
        yield "Fetching profile..."

        email_address = state["email_address"]

        photo_url = get_photo_for_email(email_address)
        if not photo_url:
            raise ValueError("Photo not found")

        state["input_image"] = photo_url

        yield from super().run(state)

        should_send_email = state.get("should_send_email")
        if should_send_email:
            from_email = state.get("email_from")
            cc_email = state.get("email_cc")
            email_subject = state.get("email_subject")
            email_body = state.get("email_body")
            send_smtp_message(
                sender=from_email if from_email else "devs@dara.network",
                to_address=email_address,
                cc_address=cc_email if cc_email else None,
                subject=email_subject
                if email_subject
                else "Thanks for joining the Gooey.AI waitlist",
                html_message=email_body
                if email_body
                else "Here's a picture of you that we found from your email address on the internet and then enhanced with AI. Want more? Contact support@gooey.ai",
                image_urls=state["output_images"],
            )
            state["email_sent"] = True


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
