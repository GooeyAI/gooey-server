import math
import mimetypes
import re
import uuid
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps
from firebase_admin import storage

import gooey_ui as st
from daras_ai_v2 import settings
from gooey_ui import UploadedFile


# @st.cache(hash_funcs={UploadedFile: lambda uploaded_file: uploaded_file.id})
# @st.cache_data
def upload_file(uploaded_file: UploadedFile):
    img_bytes, filename, content_type = uploaded_file_get_value(uploaded_file)
    img_bytes = resize_img_pad(img_bytes, (512, 512))
    return upload_file_from_bytes(filename, img_bytes, content_type=content_type)


def resize_img_pad(img_bytes: bytes, size: (int, int)) -> bytes:
    img_cv2 = bytes_to_cv2_img(img_bytes)
    img_pil = Image.fromarray(img_cv2)
    img_pil = ImageOps.pad(img_pil, size)
    img_cv2 = np.array(img_pil)
    return cv2_img_to_bytes(img_cv2)


# @st.cache(hash_funcs={UploadedFile: lambda uploaded_file: uploaded_file.id})
# @st.cache_data
def upload_file_hq(uploaded_file: UploadedFile, *, resize: (int, int) = (1024, 1024)):
    img_bytes, filename, content_type = uploaded_file_get_value(uploaded_file)
    img_bytes = resize_img_scale(img_bytes, resize)
    return upload_file_from_bytes(filename, img_bytes, content_type=content_type)


def uploaded_file_get_value(uploaded_file):
    img_bytes = uploaded_file.read()
    filename = uploaded_file.name
    content_type = uploaded_file.type
    if filename.endswith("HEIC"):
        img_bytes = _heic_to_png(img_bytes)
        filename += ".png"
        content_type = "image/png"
    return img_bytes, safe_filename(filename), content_type


def _heic_to_png(img_bytes: bytes) -> bytes:
    from wand.image import Image

    with Image(blob=img_bytes) as original:
        with original.convert("png") as converted:
            img_bytes = converted.make_blob()
    return img_bytes


def resize_img_scale(img_bytes: bytes, size: (int, int)) -> bytes:
    img_cv2 = bytes_to_cv2_img(img_bytes)
    img_pil = Image.fromarray(img_cv2)
    downscale_factor = get_downscale_factor(im_size=img_pil.size, max_size=size)
    if downscale_factor:
        img_pil = ImageOps.scale(img_pil, downscale_factor)
    img_cv2 = np.array(img_pil)
    return cv2_img_to_bytes(img_cv2)


def get_downscale_factor(*, im_size: (int, int), max_size: (int, int)) -> float | None:
    downscale_factor = math.sqrt(
        (max_size[0] * max_size[1]) / (im_size[0] * im_size[1])
    )
    if downscale_factor < 0.99:
        return downscale_factor
    else:
        return None


def resize_img_fit(img_bytes: bytes, size: (int, int)) -> bytes:
    img_cv2 = bytes_to_cv2_img(img_bytes)
    img_pil = Image.fromarray(img_cv2)
    img_pil = ImageOps.fit(img_pil, size)
    img_cv2 = np.array(img_pil)
    return cv2_img_to_bytes(img_cv2)


# @st.cache_data
def upload_st_file(f: UploadedFile) -> str:
    return upload_file_from_bytes(f.name, f.getvalue(), f.type)


def upload_file_from_bytes(
    filename: str,
    data: bytes,
    content_type: str = None,
) -> str:
    if not content_type:
        content_type = mimetypes.guess_type(filename)[0]
    content_type = content_type or "application/octet-stream"

    filename = safe_filename(filename)
    bucket = storage.bucket(settings.GS_BUCKET_NAME)
    blob = bucket.blob(f"daras_ai/media/{uuid.uuid1()}/{filename}")
    blob.upload_from_string(data, content_type=content_type)
    return blob.public_url


def storage_blob_for(filename: str) -> storage.storage.Blob:
    filename = safe_filename(filename)
    bucket = storage.bucket(settings.GS_BUCKET_NAME)
    blob = bucket.blob(f"daras_ai/media/{uuid.uuid1()}/{filename}")
    return blob


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


FILENAME_WHITELIST = re.compile(r"[ a-zA-Z0-9\-_.]")


def safe_filename(filename: str):
    matches = FILENAME_WHITELIST.finditer(filename)
    filename = "".join(match.group(0) for match in matches)
    p = Path(filename)
    out = truncate_filename(p.stem) + p.suffix
    return out


def truncate_filename(text: str, maxlen: int = 100, sep: str = "...") -> str:
    if len(text) <= maxlen:
        return text
    assert len(sep) <= maxlen
    mid = (maxlen - len(sep)) // 2
    return text[:mid] + sep + text[-mid:]


def truncate_text_words(text: str, maxlen: int, sep: str = " …") -> str:
    if len(text) <= maxlen:
        return text
    assert len(sep) <= maxlen
    match = re.match(r"^(.{0,%d}\S)(\s)" % (maxlen - len(sep) - 1), text, flags=re.S)
    if match:
        trunc = match.group(1)
    else:
        trunc = text[: maxlen - len(sep)]
    return trunc + sep
