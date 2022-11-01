import streamlit as st
from google.cloud.firestore_v1 import DocumentSnapshot

from daras_ai import settings
from daras_ai.db import list_all_docs
from daras_ai.logo import logo
from pages.ChyronPlant import ChyronPlantPage
from pages.EmailFaceInpainting import EmailFaceInpaintingPage
from pages.FaceInpainting import FaceInpaintingPage
from pages.LetterWriter import LetterWriterPage
from pages.Lipsync import LipsyncPage

assert settings.GOOGLE_APPLICATION_CREDENTIALS

logo()


st.write("---")

for page in [
    FaceInpaintingPage,
    EmailFaceInpaintingPage,
    LetterWriterPage,
    LipsyncPage,
    ChyronPlantPage,
]:
    url = page.__module__.split(".")[-1]
    st.markdown(
        f"""
        <a style="font-size: 24px" href="/{url}" target = "_self">
        {page.title}
        </a>
        <br>
        <br>
        """,
        unsafe_allow_html=True,
    )


st.write("")

with st.expander("Old Recipes"):

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
        st.markdown(
            f"""
            <a style="font-size: 24px" href="/Editor/?id={recipe_id}" target = "_self">{name}</a>
            <br>
            <i>{tagline}</i>
            """,
            unsafe_allow_html=True,
        )
