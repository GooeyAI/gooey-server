import math
import mimetypes
import re
import uuid
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageOps

from daras_ai_v2 import settings


def resize_img_pad(img_bytes: bytes, size: tuple[int, int]) -> bytes:
    img_cv2 = bytes_to_cv2_img(img_bytes)
    img_pil = Image.fromarray(img_cv2)
    img_pil = ImageOps.pad(img_pil, size)
    img_cv2 = np.array(img_pil)
    return cv2_img_to_bytes(img_cv2)


def resize_img_scale(img_bytes: bytes, size: tuple[int, int]) -> bytes:
    img_cv2 = bytes_to_cv2_img(img_bytes)
    img_pil = Image.fromarray(img_cv2)
    downscale_factor = get_downscale_factor(im_size=img_pil.size, max_size=size)
    if downscale_factor:
        img_pil = ImageOps.scale(img_pil, downscale_factor)
    img_cv2 = np.array(img_pil)
    return cv2_img_to_bytes(img_cv2)


def get_downscale_factor(
    *, im_size: tuple[int, int], max_size: tuple[int, int]
) -> float | None:
    downscale_factor = math.sqrt(
        (max_size[0] * max_size[1]) / (im_size[0] * im_size[1])
    )
    if downscale_factor < 0.99:
        return downscale_factor
    else:
        return None


def resize_img_fit(img_bytes: bytes, size: tuple[int, int]) -> bytes:
    img_cv2 = bytes_to_cv2_img(img_bytes)
    img_pil = Image.fromarray(img_cv2)
    img_pil = ImageOps.fit(img_pil, size)
    img_cv2 = np.array(img_pil)
    return cv2_img_to_bytes(img_cv2)


def upload_file_from_bytes(
    filename: str,
    data: bytes,
    content_type: str = None,
) -> str:
    from firebase_admin import storage

    if not content_type:
        content_type = mimetypes.guess_type(filename)[0]
    content_type = content_type or "application/octet-stream"

    filename = safe_filename(filename)
    bucket = storage.bucket(settings.GS_BUCKET_NAME)
    blob = bucket.blob(f"daras_ai/media/{uuid.uuid1()}/{filename}")
    blob.upload_from_string(data, content_type=content_type)
    return blob.public_url


def storage_blob_for(filename: str) -> "storage.storage.Blob":
    from firebase_admin import storage

    filename = safe_filename(filename)
    bucket = storage.bucket(settings.GS_BUCKET_NAME)
    blob = bucket.blob(f"daras_ai/media/{uuid.uuid1()}/{filename}")
    return blob


def cv2_img_to_bytes(img: np.ndarray) -> bytes:
    import cv2

    return cv2.imencode(".png", img)[1].tobytes()


def bytes_to_cv2_img(img_bytes: bytes, greyscale=False) -> np.ndarray:
    import cv2

    if greyscale:
        flags = cv2.IMREAD_GRAYSCALE
    else:
        flags = cv2.IMREAD_COLOR
    img_cv2 = cv2.imdecode(np.frombuffer(img_bytes, dtype=np.uint8), flags=flags)
    if not img_exists(img_cv2):
        raise ValueError("Bad Image")
    return img_cv2


def img_exists(img: np.ndarray | str) -> bool:
    if isinstance(img, np.ndarray):
        return bool(len(img))
    else:
        return bool(img)


FILENAME_WHITELIST = re.compile(r"[ a-zA-Z0-9\-_.]")


def safe_filename(filename: str) -> str:
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


# Add some missing mimetypes
mimetypes.add_type("audio/wav", ".wav")


def guess_ext_from_response(response: requests.Response) -> str:
    mimetype = get_mimetype_from_response(response)
    return mimetypes.guess_extension(mimetype) or ""


def get_mimetype_from_response(response: requests.Response) -> str:
    content_type = response.headers.get("Content-Type", "application/octet-stream")
    return content_type.split(";")[0]
