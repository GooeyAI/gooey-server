import base64
import io
import uuid

import cv2
from PIL import Image, ImageOps
import numpy as np
import streamlit as st
from firebase_admin import storage
from streamlit.runtime.uploaded_file_manager import UploadedFile

from daras_ai import settings
from daras_ai.core import daras_ai_step_config, daras_ai_step_io


@daras_ai_step_config("Image input", is_input=True)
def image_input(idx, variables, state):
    var_name = st.text_input(
        "Variable Name",
        value=state.get("var_name", "image_input"),
        help=f"Image name {idx}",
    )
    state.update({"var_name": var_name})

    # col1, col2 = st.columns(2)
    # with col1:
    #     resize_width = int(
    #         st.number_input(
    #             "Resize Width",
    #             step=1,
    #             value=state.get("resize_width", 512),
    #             help=f"Resize Width {idx}",
    #         )
    #     )
    #     state.update({"resize_width": resize_width})
    # with col2:
    #     resize_height = int(
    #         st.number_input(
    #             "Resize Height",
    #             step=1,
    #             value=state.get("resize_height", 512),
    #             help=f"Resize Width {idx}",
    #         )
    #     )
    #     state.update({"resize_height": resize_height})
    #


@daras_ai_step_io
def image_input(idx, variables, state):
    var_name = state.get("var_name", "")
    # resize_width = state["resize_width"]
    # resize_height = state["resize_height"]
    if not var_name:
        return
    if var_name not in variables:
        variables[var_name] = None

    uploaded_file = st.file_uploader(var_name, help=f"Image input {var_name} {idx + 1}")
    if uploaded_file:
        image_url = upload_file(uploaded_file)
        variables[var_name] = image_url

    image_url = variables.get(var_name)
    if image_url:
        st.image(variables[var_name], width=300)


@st.cache(hash_funcs={UploadedFile: lambda uploaded_file: uploaded_file.id})
def upload_file(uploaded_file):
    img_bytes = uploaded_file.getvalue()
    img_bytes = resize_img(img_bytes, (512, 512))
    return upload_file_from_bytes(uploaded_file.name, img_bytes)


def resize_img(img_bytes, size):
    im_pil = Image.open(io.BytesIO(img_bytes))
    im_pil = ImageOps.pad(im_pil, size)
    img_bytes_io = io.BytesIO()
    im_pil.save(img_bytes_io, format="png")
    img_bytes = img_bytes_io.getvalue()
    return img_bytes


def upload_file_from_bytes(filename: str, img_bytes: bytes) -> str:
    bucket = storage.bucket(settings.GS_BUCKET_NAME)
    blob = bucket.blob(f"daras_ai/media/{uuid.uuid1()}/{filename}")
    blob.upload_from_string(img_bytes)
    return blob.public_url


def cv2_img_to_png(img):
    return cv2.imencode(".png", img)[1].tobytes()


def bytes_to_cv2_img(img_bytes: bytes):
    return cv2.imdecode(np.frombuffer(img_bytes, dtype=np.uint8), flags=1)
