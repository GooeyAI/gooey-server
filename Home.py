import streamlit as st
from furl import furl
from google.cloud.firestore_v1 import DocumentSnapshot

from daras_ai.db import list_all_docs
from daras_ai.logo import logo
from daras_ai_v2 import settings
from daras_ai_v2.face_restoration import map_parallel
from pages.CompareLM import CompareLMPage
from pages.DeforumSD import DeforumSDPage
from pages.EmailFaceInpainting import EmailFaceInpaintingPage
from pages.FaceInpainting import FaceInpaintingPage
from pages.Img2Img import Img2ImgPage
from pages.Lipsync import LipsyncPage
from pages.LipsyncTTS import LipsyncTTSPage
from pages.ObjectInpainting import ObjectInpaintingPage
from pages.TextToSpeech import TextToSpeechPage

assert settings.GOOGLE_APPLICATION_CREDENTIALS

logo()

page_classes = [
    FaceInpaintingPage,
    TextToSpeechPage,
    LipsyncTTSPage,
    ObjectInpaintingPage,
    Img2ImgPage,
    DeforumSDPage,
    CompareLMPage,
    LipsyncPage,
    EmailFaceInpaintingPage,
    # ChyronPlantPage,
    # ImageSegmentationPage,
]

pages = [page_cls() for page_cls in page_classes]

with st.spinner():
    all_examples = map_parallel(lambda page: page.get_doc(), pages)

for page, example_doc in zip(pages, all_examples):
    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            f"""
            <a style="font-size: 24px" href="{furl(settings.APP_BASE_URL) / page.slug}" target = "_top">
                <h2>{page.title}</h2>
            </a>
            """,
            unsafe_allow_html=True,
        )
        page.render_description()

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
            furl(settings.APP_BASE_URL, query_params={"id": recipe_id}) / "Editor"
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
