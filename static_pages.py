import gooey_gui as gui
from daras_ai_v2 import settings
import io
import mimetypes
from starlette.requests import Request
from fastapi import HTTPException
from zipfile import ZipFile, is_zipfile
import urllib.request
from daras_ai_v2.base import BasePage


def gcs_bucket() -> "storage.storage.Bucket":
    from firebase_admin import storage

    return storage.bucket(settings.GS_BUCKET_NAME)


WEBSITE_FOLDER_PATH = "gooey-website"


def serve(page_slug: str, file_path: str):

    bucket = gcs_bucket()

    blob_path = ""
    if page_slug and not file_path:
        # If page_slug is provided, then it's a page
        blob_path = f"{WEBSITE_FOLDER_PATH}/{page_slug}.html"
    elif file_path:
        blob_path = f"{WEBSITE_FOLDER_PATH}/{file_path}"

    if not (blob_path.endswith(".html")):
        return dict(
            redirectUrl=f"https://storage.googleapis.com/{settings.GS_BUCKET_NAME}/{WEBSITE_FOLDER_PATH}/{file_path}"
        )

    static_file = bucket.get_blob(blob_path)
    if not static_file:
        return None

    blob = static_file.download_as_string()
    blob = blob.decode("utf-8")
    content = io.StringIO(blob).read()

    return dict(content=content)


class StaticPageUpload(BasePage):
    def __init__(self, request: Request):
        self.zip_file = None
        self.extracted_files = []
        self.request = request
        self.is_uploading = False

    def extract_zip_to_gcloud(self):
        bucket = gcs_bucket()
        if not self.zip_file:
            return

        # download zip file from gcloud (uppy)
        zip_file = urllib.request.urlopen(self.zip_file)
        archive = io.BytesIO()
        archive.write(zip_file.read())

        if archive and is_zipfile(archive):
            with ZipFile(archive, "r") as z:
                for file_info in z.infolist():
                    if not file_info.is_dir():
                        file_data = z.read(file_info)
                        file_name = file_info.filename  # Maintain directory structure
                        blob_path = f"{WEBSITE_FOLDER_PATH}/{file_name}"
                        blob = bucket.blob(blob_path)
                        content_type = (
                            mimetypes.guess_type(file_name)[0] or "text/plain"
                        )
                        blob.upload_from_string(file_data, content_type=content_type)
                        self.extracted_files.append(blob.public_url)

    def render_file_upload(self) -> None:
        if not BasePage.is_current_user_admin(self):
            raise HTTPException(status_code=404, detail="Not authorized")

        with gui.div(
            className="container d-flex align-items-center justify-content-center flex-column"
        ):
            self.zip_file = gui.file_uploader(
                label="Upload ZIP File",
                accept=[".zip"],
                value=self.zip_file,
            )
            pressed_save = gui.button(
                "Extract ZIP File",
                key="zip_file",
                type="primary",
                disabled=not self.zip_file,
            )
            gui.caption(
                "After successful upload, extracted files will be displayed below.",
                className="my-4 text-muted",
            )
            if pressed_save:
                self.extract_zip_to_gcloud()

            # render extracted files if any
            if self.extracted_files and len(self.extracted_files) > 0:
                gui.write("Extracted Files:")
                with gui.tag("div", className="my-4 d-flex flex-column"):
                    for extracted_file in self.extracted_files:
                        with gui.tag("div", className="bg-light p-2 my-2"):
                            with gui.tag("a", href=extracted_file):
                                gui.html(extracted_file)
