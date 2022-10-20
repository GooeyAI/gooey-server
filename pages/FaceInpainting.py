import replicate
import requests
import streamlit as st
from streamlit.runtime.uploaded_file_manager import UploadedFile

from daras_ai.extract_face import extract_face_cv2
from daras_ai.image_input import (
    resize_img,
    bytes_to_cv2_img,
    cv2_img_to_png,
    upload_file_from_bytes,
)
from daras_ai.logo import logo

st.set_page_config(layout="wide")


def main():
    logo()

    st.write(
        """
        """
    )

    col1, col2 = st.columns(2)

    with col1:
        st.write(
            """
            ### Prompt
            Describe the character that you'd like to generate
            """
        )
        st.text_input(
            "",
            label_visibility="collapsed",
            key="text_prompt",
            placeholder="Iron man",
        )

        st.write(
            """
            ### Face Photo
            Give us a photo of yourself, or anyone else
            """
        )
        st.file_uploader(
            "",
            label_visibility="collapsed",
            key="input_images",
            accept_multiple_files=True,
        )
        st.caption(
            "By uploading an image, you agree to Dara's [Privacy Policy](https://dara.network/privacy)"
        )

        show_input_images()

    with col2:
        submit = st.button("Submit 🚀")
        if submit:

            input_images: list[UploadedFile] | None = st.session_state.get(
                "input_images"
            )
            text_prompt: str = st.session_state.get("text_prompt")
            if not (text_prompt and input_images):
                st.write("Please provide a Prompt and a Face Photo!")
                return

            # st.write(input_images)
            # on_submit(input_images, text_prompt)
            # st.image(input_images, width=200)

            st.markdown(
                f"""
                <img src="pic_trulli.jpg" alt="Italian Trulli">
                """,
                unsafe_allow_html=True,
            )

        output_images = st.session_state.get("output_images")
        if not output_images:
            return
        st.write(
            """
            ### Generated Photos
            """
        )
        for url in output_images:
            st.image(url, width=200)


def show_input_images():
    input_images: list[UploadedFile] | None = st.session_state.get("input_images")
    if not input_images:
        return

    # input_image_urls = [upload_file(file) for file in input_images]
    # st.session_state["input_image_url"] = input_image_urls

    for url in input_images:
        st.image(url, width=200)


def on_submit(input_images: list[UploadedFile], text_prompt: str) -> list[str]:
    for file in input_images:
        resized_img_bytes = resize_img(file.getvalue(), (512, 512))
        resized_img_url = upload_file_from_bytes(file.name, resized_img_bytes)

        image_cv2 = bytes_to_cv2_img(resized_img_bytes)
        face_mask_cv2 = extract_face_cv2(image_cv2)
        face_mask_bytes = cv2_img_to_png(face_mask_cv2)
        face_mask_url = upload_file_from_bytes("face_mask.png", face_mask_bytes)

        model = replicate.models.get("devxpy/glid-3-xl-stable").versions.get(
            "d53d0cf59b46f622265ad5924be1e536d6a371e8b1eaceeebc870b6001a0659b"
        )
        output_photos = model.predict(
            prompt=text_prompt,
            num_outputs=1,
            edit_image=resized_img_url,
            mask=face_mask_url,
            num_inference_steps=10,
        )

        for url in output_photos:
            url = upload_file_from_bytes("out.png", requests.get(url).content)


main()
