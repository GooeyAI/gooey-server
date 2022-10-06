import streamlit as st
from google.cloud import firestore
import streamlit.components.v1 as components
from google.cloud.firestore_v1 import DocumentSnapshot

import daras_ai

db = firestore.Client()
db_collection = db.collection("daras-ai--political_example")


def open_document(doc_id):
    components.html(
        f"""
        <script>
            let new_url = "/Editor/?id={doc_id}";
            window.open(new_url, "_blank");
        </script>
        """,
        width=0,
        height=0,
    )


for item in db_collection.get():
    item: DocumentSnapshot
    doc = item.to_dict()

    name = doc.get("header_title")
    if not name:
        continue

    st.button(
        name,
        help=f"{doc.get('header_desc')} ({item.id})",
        on_click=open_document,
        args=[item.id],
    )
