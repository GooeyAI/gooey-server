import io
from static_pages.models import StaticPage
from google.cloud import storage

from bs4 import BeautifulSoup
from daras_ai_v2.settings import GCP_PROJECT, GCS_CREDENTIALS, GS_BUCKET_NAME


def gcs_bucket() -> "storage.storage.Bucket":
    client = storage.Client(
        GCP_PROJECT,
        GCS_CREDENTIALS,
    )
    bucket = client.get_bucket(GS_BUCKET_NAME)
    return bucket


def populate_imported_css(html: str, uid: str):
    soup = BeautifulSoup(html, "html.parser")
    links = soup.find_all("link")
    hrefList = [link.get("href") for link in links if link.get("href") is not None]
    # Remove all <link> tags
    for link in links:
        link.decompose()

    styles = get_all_styles(hrefList, uid)
    style_tag = BeautifulSoup(styles, "html.parser").style
    # Insert the style tag into the body
    if soup.body:
        soup.body.insert(0, style_tag)
    else:
        # If body tag does not exist, create it and add style tag
        body_tag = soup.new_tag("body")
        body_tag.insert(0, style_tag)
        soup.append(body_tag)

    return soup


def get_all_styles(links: list, uid: str):
    styles = ""
    for link in links:
        if not link.endswith(".css"):  # ignore for css files
            continue
        blob = gcs_bucket().get_blob(f"{uid}/{link}")
        blob = blob.download_as_string()
        blob = blob.decode("utf-8")
        blob = io.StringIO(blob).read()
        styles += blob

    return f"<style>{styles}</style>"


def serve(page_slug: str, file_path: str = None):
    static_page = StaticPage.objects.get(path=page_slug)

    if not static_page:
        return None

    uid = static_page.uid
    bucket = gcs_bucket()

    def render_page():
        if file_path:
            return None
        html = None
        blob = bucket.get_blob(f"{uid}/index.html")
        blob = blob.download_as_string()
        blob = blob.decode("utf-8")
        html = io.StringIO(blob).read()
        withStyleHtml = populate_imported_css(
            html, uid
        )  # Add all the styles in the html

        return withStyleHtml

    def get_file_url():
        if not file_path:
            return None
        STATIC_URL = f"https://storage.googleapis.com/gooey-test/{uid}"
        return f"{STATIC_URL}/{file_path}"

    return render_page(), get_file_url()
