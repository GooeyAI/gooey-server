import mimetypes
import os
import typing

from furl import furl


PreviewSizes = typing.Literal[
    "400x400", "1170x1560", "40x40", "72x72", "80x80", "96x96"
]


def media_preview_img(
    file_url: str | None, size: PreviewSizes = "400x400"
) -> str | None:
    from daras_ai_v2.doc_search_settings_widgets import is_user_uploaded_url

    if not (file_url and is_user_uploaded_url(file_url)):
        return None

    f = furl(file_url.strip("/"))
    segments = f.path.segments
    if not segments:
        return None
    dir_segments = segments[:-1]
    basename = segments[-1]
    base, ext = os.path.splitext(basename)
    content_type = mimetypes.guess_type(basename)[0] or ""

    if content_type.startswith("video/"):
        f.path.segments = dir_segments + ["thumbs", f"{base}.gif"]
        return str(f)
    elif content_type in {"image/png", "image/jpeg", "image/tiff", "image/webp"}:
        f.path.segments = dir_segments + ["thumbs", f"{base}_{size}{ext}"]
        return str(f)

    return None
