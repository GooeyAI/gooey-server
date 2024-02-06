import mimetypes
import os
import typing

from furl import furl


def meta_preview_url(
    file_url: str | None,
    fallback_img: str = None,
    size: typing.Literal[
        "400x400", "1170x1560", "40x40", "72x72", "80x80", "96x96"
    ] = "400x400",
) -> str | None:
    if not file_url:
        return fallback_img

    f = furl(file_url)
    dir_segments = f.path.segments[:-1]
    basename = f.path.segments[-1]
    base, ext = os.path.splitext(basename)
    content_type = mimetypes.guess_type(basename)[0] or ""

    if content_type.startswith("video/"):
        f.path.segments = dir_segments + ["thumbs", f"{base}.gif"]
        # fallback to default image if video gif not present
        file_url = fallback_img
    elif content_type in ["image/png", "image/jpeg", "image/tiff", "image/webp"]:
        # sizes:  400x400,1170x1560,40x40,72x72,80x80,96x96
        f.path.segments = dir_segments + ["thumbs", f"{base}_{size}{ext}"]

    new_url = str(f)
    return new_url
    ## this is too costly to do for every api call
    # r = requests.head(new_url)
    # if r.status_code == 200:
    #     return new_url
    # else:
    #     return file_url
