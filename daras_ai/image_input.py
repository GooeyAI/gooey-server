import math
import mimetypes
import os
import re
import typing
import uuid
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageOps
from furl import furl

from daras_ai_v2 import gcs_v2, settings
from daras_ai_v2.exceptions import UserError
from files.models import FileMetadata, UploadedFile

if typing.TYPE_CHECKING:
    from google.cloud.storage import Blob, Bucket
    from app_users.models import AppUser
    from workspaces.models import Workspace


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
    *,
    workspace: typing.Optional["Workspace"] = None,
    user: typing.Optional["AppUser"] = None,
    is_user_uploaded: bool = False,
) -> str:
    blob = gcs_blob_for(filename)
    upload_gcs_blob_from_bytes(
        blob,
        data,
        content_type,
        filename=filename,
        workspace=workspace,
        user=user,
        is_user_uploaded=is_user_uploaded,
    )
    return blob.public_url


def gcs_blob_for(filename: str) -> "Blob":
    filename = safe_filename(filename)
    bucket = gcs_bucket()
    blob = bucket.blob(
        os.path.join(settings.GS_MEDIA_PATH, str(uuid.uuid1()), filename)
    )
    return blob


def upload_gcs_blob_from_bytes(
    blob: "Blob",
    data: bytes,
    content_type: str = None,
    *,
    filename: str | None = None,
    workspace: typing.Optional["Workspace"] = None,
    user: typing.Optional["AppUser"] = None,
    is_user_uploaded: bool = False,
) -> str:
    if not content_type:
        content_type = mimetypes.guess_type(blob.path)[0]
    content_type = content_type or "application/octet-stream"
    blob.upload_from_string(data, content_type=content_type)
    register_uploaded_blob(
        blob,
        filename=filename,
        content_type=content_type,
        total_bytes=len(data),
        workspace=workspace,
        user=user,
        is_user_uploaded=is_user_uploaded,
    )
    return blob.public_url


def register_uploaded_blob(
    blob: "Blob",
    *,
    filename: str | None = None,
    content_type: str | None = None,
    total_bytes: int | None = None,
    workspace: typing.Optional["Workspace"] = None,
    user: typing.Optional["AppUser"] = None,
    is_user_uploaded: bool = False,
    is_uploading: bool = False,
) -> UploadedFile:
    if not blob.name or not blob.bucket:
        raise ValueError("Blob must have bucket and name set before registration.")

    from celeryapp.tasks import get_running_saved_run

    saved_run = get_running_saved_run()
    if saved_run:
        if workspace is None:
            workspace = saved_run.workspace
        if user is None and saved_run.uid:
            from app_users.models import AppUser

            user = AppUser.objects.filter(uid=saved_run.uid).first()
    if content_type is None:
        content_type = getattr(blob, "content_type", None)
    if total_bytes is None:
        total_bytes = getattr(blob, "size", None)
    etag = getattr(blob, "etag", None)

    content_type = (
        content_type or mimetypes.guess_type(blob.name)[0] or "application/octet-stream"
    )
    total_bytes = total_bytes or 0

    bucket_name = blob.bucket.name
    object_name = blob.name

    metadata = FileMetadata.objects.create(
        name=filename or Path(blob.name).name,
        etag=etag,
        mime_type=content_type,
        total_bytes=total_bytes,
    )
    uploaded, created = UploadedFile.objects.get_or_create(
        bucket_name=bucket_name,
        object_name=object_name,
        defaults=dict(
            metadata=metadata,
            f_url=blob.public_url,
            saved_run=saved_run,
            workspace=workspace,
            user=user,
            is_user_uploaded=is_user_uploaded,
            is_uploading=is_uploading,
        ),
    )
    if not created:
        metadata.delete()
    return uploaded


def get_uploaded_file_for_blob(blob: "Blob") -> typing.Optional[UploadedFile]:
    if not blob.name or not blob.bucket:
        return None
    return UploadedFile.objects.filter(
        bucket_name=blob.bucket.name, object_name=blob.name
    ).first()


def delete_uploaded_file_for_blob(blob: "Blob") -> bool:
    uploaded = get_uploaded_file_for_blob(blob)
    if not uploaded:
        return False
    uploaded.delete()
    return True


def delete_uploaded_file_for_gcs_url(url: str) -> bool:
    segments = [seg for seg in furl(url).path.segments if seg]
    if not segments:
        return False
    bucket_name = segments[0]
    object_name = "/".join(segments[1:])
    if not object_name:
        return False
    uploaded = UploadedFile.objects.filter(
        bucket_name=bucket_name, object_name=object_name
    ).first()
    if not uploaded:
        return False
    uploaded.delete()
    return True


def gcs_bucket() -> "Bucket":
    from firebase_admin import storage

    return storage.bucket(settings.GS_BUCKET_NAME)


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
        raise UserError("Bad Image")
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


def truncate_filename(
    text: str | bytes, maxlen: int = 100, sep: str | bytes = "..."
) -> str | bytes:
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
    content_type = response.headers.get("Content-Type", "")
    content_type = content_type.split(";")[0]
    if content_type in gcs_v2.dumb_content_types:
        content_type = ""
    return content_type


def gs_url_to_uri(url: str) -> str:
    return "gs://" + "/".join(furl(url).path.segments)
