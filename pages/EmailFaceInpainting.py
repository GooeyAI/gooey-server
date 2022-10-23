import smtplib
from copy import deepcopy
from time import time

import replicate
import requests
import streamlit as st
from decouple import config
from pydantic import BaseModel

from daras_ai.extract_face import extract_face_cv2
from daras_ai.face_restoration import map_parallel, gfpgan
from daras_ai.image_input import (
    resize_img,
    bytes_to_cv2_img,
    cv2_img_to_png,
    upload_file_from_bytes,
)
from daras_ai.logo import logo
from daras_ai_v2.base import get_saved_state, run_as_api_tab, save_button
from daras_ai_v2.send_email import send_smtp_message
from pages import FaceInpainting

DOC_NAME = "EmailFaceInpainting"
API_URL = "/v1/EmailFaceInpainting/run"


class RequestModel(BaseModel):
    email_address: str
    text_prompt: str

    num_outputs: int = 1
    quality: int = 50

    class Config:
        schema_extra = {
            "example": {
                "text_prompt": "winter's day in paris",
                "email_address": "sean@dara.network",
            }
        }


class ResponseModel(BaseModel):
    resized_image: str
    face_mask: str
    output_images: list[str]


def main():
    logo()

    if not st.session_state:
        st.session_state.update(deepcopy(get_saved_state(DOC_NAME)))
    st.session_state.setdefault("num_steps", 50)

    save_button(DOC_NAME)

    tab1, tab2, tab3 = st.tabs(["🏃‍♀️ Run", "⚙️ Settings", "🚀 Run as API"])

    with tab1:
        run_tab()

    with tab2:
        edit_tab()

    with tab3:
        run_as_api_tab(API_URL, RequestModel)


def run_tab():
    st.write(
        """
### Email of You in Paris

*EmailID > Profile pic > Face Masking > Stable Diffusion > GFPGAN*  

This recipe takes only an email address and returns a photo of the person with that email, rendered on winter's day in Paris.

How It Works:

1. Calls social media APIs to get a user's twitter, facebook, linkedin or insta profile photo 
2. Extracts faces from any image using MediaPipe
3. Generates images from the given prompt and inpaints with Stable diffusion
4. Improves faces using gfpgan    
"""
    )

    with st.form("my_form"):
        st.write(
            """
            ### Prompt
            Describe the character that you'd like to generate. 
            """
        )
        st.text_input(
            "",
            label_visibility="collapsed",
            key="text_prompt",
            placeholder="winter's day in paris",
        )

        st.write(
            """
            ### Email Address
            Give us your email address, and we'll try to get your photo 
            """
        )
        st.text_input(
            "",
            label_visibility="collapsed",
            key="email_address",
            placeholder="john@appleseed.com",
        )
        st.caption(
            "By providing your email address, you agree to Dara's [Privacy Policy](https://dara.network/privacy)"
        )

        col1, col2 = st.columns(2)

        with col1:
            st.slider(label="# of Outputs", key="num_outputs", min_value=1, max_value=4)
        with col2:
            st.slider(
                label="Quality",
                key="num_steps",
                min_value=10,
                max_value=200,
                step=10,
            )

        submitted = st.form_submit_button("🚀 Submit")

    msg_container = st.container()

    gen = None
    start = time()
    if submitted:
        text_prompt = st.session_state.get("text_prompt")
        email_address = st.session_state.get("email_address")
        if not (text_prompt and email_address):
            with msg_container:
                st.error("Please provide a Prompt and your Email Address", icon="⚠️")
        else:
            gen = run(st.session_state)

    col1, col2 = st.columns(2)

    with col1:
        if gen:
            with st.spinner():
                try:
                    next(gen)
                except ValueError as e:
                    with msg_container:
                        st.error(str(e), icon="⚠️")
                        return
        if "input_image" in st.session_state:
            st.image(st.session_state["input_image"], caption="Input Image")

    with col2:
        if gen:
            with st.spinner():
                for _ in range(3):
                    next(gen)
        if "output_images" in st.session_state:
            for url in st.session_state["output_images"]:
                st.image(url, caption=st.session_state.get("text_prompt", ""))

    if gen:
        time_taken = time() - start
        with msg_container:
            st.success(
                f"Success! Run Time: `{time_taken:.1f}` seconds. "
                f"This GPU time is free while we're building daras.ai, Enjoy!",
                icon="✅",
            )

    if gen:
        with st.spinner("Sending email..."):
            next(gen)
        st.write(f"✅ Email sent to {st.session_state.get('email_address')}")


def edit_tab():
    st.write(
        """
        ### From Email
        """
    )
    st.text_input(
        "",
        label_visibility="collapsed",
        key="from_email_prompt",
    )


def run(state: dict):
    email_address = state["email_address"]

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
        raise ValueError("Photo not found")

    state["input_image"] = photo_url

    yield

    yield from FaceInpainting.run(state)

    send_smtp_message(
        sender="devs@dara.network",
        to_address=email_address,
        subject="Thanks for joining the Daras.AI waitlist",
        html_message="Here's a picture of you that we found from your email address on the internet and then enhanced with AI. Want more? Contact sean@dara.network",
        image_urls=state["output_images"],
    )

    yield


if __name__ == "__main__":
    main()
