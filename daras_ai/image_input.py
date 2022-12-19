import re
import uuid
from pathlib import Path

import cv2
import numpy as np
import streamlit as st
from PIL import Image, ImageOps
from firebase_admin import storage
from streamlit.runtime.uploaded_file_manager import UploadedFile

from daras_ai.core import daras_ai_step_config, daras_ai_step_io
from daras_ai_v2 import settings


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
def upload_file(uploaded_file: UploadedFile):
    img_bytes, filename = uploaded_file_get_value(uploaded_file)
    img_bytes = resize_img_pad(img_bytes, (512, 512))
    return upload_file_from_bytes(filename, img_bytes)


def resize_img_pad(img_bytes: bytes, size: (int, int)) -> bytes:
    img_cv2 = bytes_to_cv2_img(img_bytes)
    img_pil = Image.fromarray(img_cv2)
    img_pil = ImageOps.pad(img_pil, size)
    img_cv2 = np.array(img_pil)
    return cv2_img_to_bytes(img_cv2)


@st.cache(hash_funcs={UploadedFile: lambda uploaded_file: uploaded_file.id})
def upload_file_hq(uploaded_file: UploadedFile, *, resize: (int, int) = (1024, 1024)):
    img_bytes, filename = uploaded_file_get_value(uploaded_file)
    img_bytes = resize_img_contain(img_bytes, resize)
    return upload_file_from_bytes(filename, img_bytes)


def uploaded_file_get_value(uploaded_file):
    img_bytes = uploaded_file.read()
    filename = uploaded_file.name
    if filename.endswith("HEIC"):
        img_bytes = _heic_to_png(img_bytes)
        filename += ".png"
    return img_bytes, safe_filename(filename)


def _heic_to_png(img_bytes: bytes) -> bytes:
    from wand.image import Image

    with Image(blob=img_bytes) as original:
        with original.convert("png") as converted:
            img_bytes = converted.make_blob()
    return img_bytes


def resize_img_contain(img_bytes: bytes, size: (int, int)) -> bytes:
    img_cv2 = bytes_to_cv2_img(img_bytes)
    img_pil = Image.fromarray(img_cv2)
    img_pil = ImageOps.contain(img_pil, size)
    img_cv2 = np.array(img_pil)
    return cv2_img_to_bytes(img_cv2)


def upload_file_from_bytes(filename: str, img_bytes: bytes) -> str:
    filename = safe_filename(filename)
    bucket = storage.bucket(settings.GS_BUCKET_NAME)
    blob = bucket.blob(f"daras_ai/media/{uuid.uuid1()}/{filename}")
    blob.upload_from_string(img_bytes)
    return blob.public_url


def cv2_img_to_bytes(img):
    return cv2.imencode(".png", img)[1].tobytes()


def bytes_to_cv2_img(img_bytes: bytes):
    img_cv2 = cv2.imdecode(np.frombuffer(img_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if not img_exists(img_cv2):
        raise ValueError("Bad Image")
    return img_cv2


def img_exists(img) -> bool:
    if isinstance(img, np.ndarray):
        return bool(len(img))
    else:
        return bool(img)


FILENAME_WHITELIST = re.compile(r"[ \w\-_.]")


def safe_filename(filename: str):
    matches = FILENAME_WHITELIST.finditer(filename)
    filename = "".join(match.group(0) for match in matches)
    p = Path(filename)
    out = _truncate(p.stem) + p.suffix
    return out


def _truncate(text: str, maxlen: int = 100) -> str:
    if len(text) < maxlen:
        return text
    mid = maxlen // 2
    return text[: mid - 3] + "..." + text[-mid:]
