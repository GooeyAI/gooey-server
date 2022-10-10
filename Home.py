import streamlit as st
from google.cloud import firestore
from google.cloud.firestore_v1 import DocumentSnapshot

from daras_ai import settings
from daras_ai.logo import logo

assert settings.GOOGLE_APPLICATION_CREDENTIALS

logo()

db = firestore.Client()
db_collection = db.collection("daras-ai--political_example")

if "docs" not in st.session_state:
    with st.spinner("Loading..."):
        st.session_state["docs"] = db_collection.where("header_title", "!=", "").get()

for snapshot in st.session_state["docs"]:
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
