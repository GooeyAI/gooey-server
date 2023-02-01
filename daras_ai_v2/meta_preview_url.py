import mimetypes
import os

import requests
from furl import furl


def meta_preview_url(file_url: str | None) -> str | None:
    if not file_url:
        return

    f = furl(file_url)
    dir_segments = f.path.segments[:-1]
    basename = f.path.segments[-1]
    base, ext = os.path.splitext(basename)
    content_type = mimetypes.guess_type(basename)[0] or ""

    if content_type.startswith("video/"):
        f.path.segments = dir_segments + ["thumbs", f"{base}.gif"]
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

