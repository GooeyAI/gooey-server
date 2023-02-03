import mimetypes
import os

import requests
from furl import furl

DEFAULT_META_IMG = (
    # "https://storage.googleapis.com/dara-c1b52.appspot.com/meta_tag_default_img.jpg"
    "https://storage.googleapis.com/dara-c1b52.appspot.com/meta_tag_gif.gif"
)


def meta_preview_url(file_url: str | None, fallback_img: str | None) -> str | None:
    if not file_url:
        return DEFAULT_META_IMG

    f = furl(file_url)
    dir_segments = f.path.segments[:-1]
    basename = f.path.segments[-1]
    base, ext = os.path.splitext(basename)
    content_type = mimetypes.guess_type(basename)[0] or ""

    if content_type.startswith("video/"):
        f.path.segments = dir_segments + ["thumbs", f"{base}.gif"]
        # fallback to default image if video gif not present
        file_url = fallback_img or DEFAULT_META_IMG
    else:
        # sizes:  400x400,1170x1560,40x40,72x72,80x80,96x96
        size = "400x400"
        f.path.segments = dir_segments + ["thumbs", f"{base}_{size}{ext}"]

    new_url = str(f)
    r = requests.head(new_url)
    if r.status_code == 200:
        return new_url
    else:
        return file_url
