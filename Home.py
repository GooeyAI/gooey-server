import streamlit as st

from recipes.VideoBots import VideoBotsPage
from server import normalize_slug, page_map

# try to load page from query params
#
query_params = st.experimental_get_query_params()
try:
    page_slug = normalize_slug(query_params["page_slug"][0])
except KeyError:
    pass
else:
    try:
        page = page_map[page_slug]
    except KeyError:
        st.error(f"## 404 - Page {page_slug!r} Not found")
    else:
        page().render()
    st.stop()

from furl import furl
from google.cloud.firestore_v1 import DocumentSnapshot

from daras_ai.db import list_all_docs
from daras_ai.init import init_scripts
from daras_ai_v2 import settings
from daras_ai_v2.face_restoration import map_parallel
from recipes.CompareText2Img import CompareText2ImgPage
from recipes.DeforumSD import DeforumSDPage
from recipes.EmailFaceInpainting import EmailFaceInpaintingPage
from recipes.FaceInpainting import FaceInpaintingPage
from recipes.GoogleImageGen import GoogleImageGenPage
from recipes.ImageSegmentation import ImageSegmentationPage
from recipes.Img2Img import Img2ImgPage
from recipes.LipsyncTTS import LipsyncTTSPage
from recipes.ObjectInpainting import ObjectInpaintingPage
from recipes.SEOSummary import SEOSummaryPage
from recipes.SocialLookupEmail import SocialLookupEmailPage
from recipes.TextToSpeech import TextToSpeechPage

assert settings.GOOGLE_APPLICATION_CREDENTIALS

init_scripts()

page_classes = [
    VideoBotsPage,
    SEOSummaryPage,
    GoogleImageGenPage,
    CompareText2ImgPage,
    FaceInpaintingPage,
    EmailFaceInpaintingPage,
    SocialLookupEmailPage,
    TextToSpeechPage,
    LipsyncTTSPage,
    ObjectInpaintingPage,
    ImageSegmentationPage,
    Img2ImgPage,
    DeforumSDPage,
    # CompareLMPage,
    # LipsyncPage,
    # ChyronPlantPage,
]

pages = [page_cls() for page_cls in page_classes]

with st.spinner():
    all_examples = map_parallel(lambda page: page.get_recipe_doc().to_dict(), pages)

for page, example_doc in zip(pages, all_examples):
    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            f"""
            <a style="font-size: 24px" href="{page.app_url()}" target = "_top">
                <h2>{page.title}</h2>
            </a>
            """,
            unsafe_allow_html=True,
        )
        page.render_preview_description()

    with col2:
        page.render_example(example_doc)
    st.write("---")

st.write("")

with st.expander("Early Recipes"):
    for snapshot in list_all_docs():
        snapshot: DocumentSnapshot

        recipe_id = snapshot.id
        doc = snapshot.to_dict()

        if doc.get("header_is_hidden"):
            continue
        name = doc.get("header_title", doc.get(""))
        if not name:
            continue

        tagline = doc.get("header_tagline", "")
        editor_url = (
            furl(settings.APP_BASE_URL, query_params={"id": recipe_id}) / "Editor/"
        )

        st.markdown(
            f"""
            <a style="font-size: 24px" href="{editor_url}" target = "_top">
                {name}
            </a>
            <br>
            <i>{tagline}</i>
            """,
            unsafe_allow_html=True,
        )
