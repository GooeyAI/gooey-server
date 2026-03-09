import mimetypes
import os
import re
import typing

from furl import furl

_THUMB_SIZE_RE = re.compile(r"^(.+)_(\d+x\d+)(\.[^.]+)$")

PreviewSizes = typing.Literal[
    "400x400", "1170x1560", "40x40", "72x72", "80x80", "96x96"
]

GCS_HOST = "storage.googleapis.com"

DEFAULT_META_IMG = (
    # Small
    "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/ec2100aa-1f6e-11ef-ba0b-02420a000159/thumbs/Main_400x400.jpg"
    # "https://storage.googleapis.com/dara-c1b52.appspot.com/meta_tag_default_img.jpg"
    # Big
    # "https://storage.googleapis.com/dara-c1b52.appspot.com/meta_tag_gif.gif"
)


def meta_preview_url(
    file_url: str | None,
    fallback_img: str = DEFAULT_META_IMG,
    size: PreviewSizes = "400x400",
) -> tuple[str | None, bool]:
    if not file_url:
        return fallback_img, False

    f = furl(file_url)
    segments = f.path.segments
    if not segments:
        return file_url, False

    if (f.host or "").lower() != GCS_HOST:
        return file_url, False

    if "thumbs" in segments:
        # For image thumbs: rewrite size suffix if it doesn't match requested size
        m = _THUMB_SIZE_RE.match(segments[-1])
        if m and m.group(2) != size:
            f.path.segments = segments[:-1] + [f"{m.group(1)}_{size}{m.group(3)}"]
            return str(f), False
        return file_url, False

    dir_segments = segments[:-1]
    basename = segments[-1]
    base, ext = os.path.splitext(basename)
    content_type = mimetypes.guess_type(basename)[0] or ""

    if content_type.startswith("video/"):
        f.path.segments = dir_segments + ["thumbs", f"{base}.gif"]
        return str(f), True
    if content_type in {"image/png", "image/jpeg", "image/tiff", "image/webp"}:
        f.path.segments = dir_segments + ["thumbs", f"{base}_{size}{ext}"]
        return str(f), False
    return file_url, False
