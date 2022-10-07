import streamlit as st
from google.cloud import firestore
from google.cloud.firestore_v1 import DocumentSnapshot

db = firestore.Client()
db_collection = db.collection("daras-ai--political_example")


if "docs" not in st.session_state:
    with st.spinner("Loading..."):
        st.session_state["docs"] = db_collection.where("header_title", "!=", "").get()

for snapshot in st.session_state["docs"]:
    snapshot: DocumentSnapshot

    recipie_id = snapshot.id
    doc = snapshot.to_dict()

    name = doc.get("header_title")
    if not name:
        continue

    st.markdown(
        f"""
        <a href="/Editor/?id={recipie_id}" target = "_self">{name}</a>
        """,
        unsafe_allow_html=True,
    )
