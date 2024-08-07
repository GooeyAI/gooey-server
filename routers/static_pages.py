import io
import os.path
from zipfile import ZipFile, is_zipfile, ZipInfo

import gooey_gui as gui
import requests
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import (
    RedirectResponse,
    HTMLResponse,
    PlainTextResponse,
    Response,
)
from starlette.status import HTTP_308_PERMANENT_REDIRECT, HTTP_401_UNAUTHORIZED

from daras_ai.image_input import gcs_bucket, upload_gcs_blob_from_bytes
from daras_ai.text_format import format_number_with_suffix
from daras_ai_v2 import settings
from daras_ai_v2.exceptions import raise_for_status
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.user_date_widgets import render_local_dt_attrs
from routers.custom_api_router import CustomAPIRouter

app = CustomAPIRouter()


def serve_static_file(request: Request) -> Response | None:
    bucket = gcs_bucket()

    relpath = request.url.path.strip("/") or "index"
    gcs_path = os.path.join(settings.GS_STATIC_PATH, relpath)

    # if the path has no extension, try to serve a .html file
    if not os.path.splitext(relpath)[1]:
        # relative css/js paths in html won't work if a trailing slash is present in the url
        if request.url.path.lstrip("/").endswith("/"):
            return RedirectResponse(
                os.path.join("/", relpath),
                status_code=HTTP_308_PERMANENT_REDIRECT,
            )
        html_url = bucket.blob(gcs_path + ".html").public_url
        r = requests.get(html_url)
        if r.ok:
            html = r.content.decode()
            # replace sign in button with user's name if logged in
            if request.user and not request.user.is_anonymous:
                html = html.replace(
                    ">Sign in<",
                    f">Hi, {request.user.first_name()  or request.user.email or request.user.phone_number or 'Anon'}<",
                    1,
                )
            return HTMLResponse(html, status_code=r.status_code)

    blob = bucket.blob(gcs_path)
    if blob.exists():
        return RedirectResponse(
            blob.public_url, status_code=HTTP_308_PERMANENT_REDIRECT
        )

    raise HTTPException(status_code=404)


@gui.route(app, "/internal/webflow-upload/")
def webflow_upload(request: Request):
    from daras_ai_v2.base import BasePage
    from routers.root import page_wrapper

    if not (request.user and BasePage.is_user_admin(request.user)):
        return PlainTextResponse("Not authorized", status_code=HTTP_401_UNAUTHORIZED)

    with page_wrapper(request), gui.div(
        className="d-flex align-items-center justify-content-center flex-column"
    ):
        render_webflow_upload()


def render_webflow_upload():
    zip_file = gui.file_uploader(label="##### Upload ZIP File", accept=[".zip"])
    pressed_save = gui.button(
        "Extract ZIP File",
        key="zip_file",
        type="primary",
        disabled=not zip_file,
    )
    if pressed_save:
        extract_zip_to_gcloud(zip_file)

    gui.caption(
        "After successful upload, files will be displayed below.",
        className="my-4 text-muted",
    )

    bucket = gcs_bucket()
    blobs = list(bucket.list_blobs(prefix=settings.GS_STATIC_PATH))
    blobs.sort(key=lambda b: (b.name.count("/"), b.name))

    with (
        gui.tag("table", className="my-4 table table-striped table-sm"),
        gui.tag("tbody"),
    ):
        for blob in blobs:
            with gui.tag("tr"):
                with gui.tag("td"):
                    gui.html("...", **render_local_dt_attrs(blob.updated))
                with gui.tag("td"), gui.tag("code"):
                    gui.html(format_number_with_suffix(blob.size) + "B")
                with gui.tag("td"), gui.tag("code"):
                    gui.html(blob.content_type)
                with (
                    gui.tag("td"),
                    gui.tag("a", href=blob.public_url),
                ):
                    gui.html(blob.name.removeprefix(settings.GS_STATIC_PATH))


def extract_zip_to_gcloud(url: str):
    r = requests.get(url)
    try:
        raise_for_status(r)
    except requests.HTTPError as e:
        gui.error(str(e))
        return
    f = io.BytesIO(r.content)
    if not (f and is_zipfile(f)):
        gui.error("Invalid ZIP file.")
        return

    bucket = gcs_bucket()
    with ZipFile(f) as zipfile:
        files = [
            file_info for file_info in zipfile.infolist() if not file_info.is_dir()
        ]
        uploaded = set(
            map_parallel(lambda file_info: upload_zipfile(zipfile, file_info), files)
        )

    # clear old files
    for blob in bucket.list_blobs(prefix=settings.GS_STATIC_PATH):
        if blob.name not in uploaded:
            blob.delete()


def upload_zipfile(zipfile: ZipFile, file_info: ZipInfo):
    filename = file_info.filename
    bucket = gcs_bucket()
    blob = bucket.blob(os.path.join(settings.GS_STATIC_PATH, filename))
    data = zipfile.read(file_info)
    upload_gcs_blob_from_bytes(blob, data)
    return blob.name
