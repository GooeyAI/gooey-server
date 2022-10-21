import json
import shlex
import typing
from copy import deepcopy
from threading import Thread

import requests
import streamlit as st
from furl import furl
from google.cloud import firestore
from pydantic import BaseModel
from streamlit.runtime.uploaded_file_manager import UploadedFile

from daras_ai_v2 import settings


def logo():
    st.markdown(
        """
        <style>
        footer {visibility: hidden;}
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <a href="/" target="_self">
            <img width=150 src="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/logo.webp"></img>
        </a>
        <a style="position: absolute; right: 0px" href="https://dara.network/privacy/">Privacy Policy</a>
        """,
        unsafe_allow_html=True,
    )
    st.write("")


def save_button(
    doc_name: str,
):
    pressed_save = st.button(" 💾 Save")
    if pressed_save:
        updated_state = deepcopy(st.session_state.to_dict())
        updated_state = {
            k: v for k, v in updated_state.items() if not k.startswith("FormSubmitter:")
        }
        Thread(target=_save_me, args=[doc_name, updated_state]).start()


def _save_me(doc_name: str, updated_state: dict):
    db = firestore.Client()
    db_collection = db.collection("daras-ai-v2")
    doc_ref = db_collection.document(doc_name)

    doc_ref.set(updated_state)

    saved_state = get_saved_state(doc_name)
    saved_state.clear()
    saved_state.update(updated_state)


@st.cache(allow_output_mutation=True)
def get_saved_state(doc_name: str) -> dict:
    db = firestore.Client()
    db_collection = db.collection("daras-ai-v2")
    doc_ref = db_collection.document(doc_name)
    doc = doc_ref.get()
    if not doc.exists:
        doc_ref.create({})
        doc = doc_ref.get()
    return doc.to_dict()


def run_as_api_tab(api_url: str, request_model: typing.Type[BaseModel]):
    api_url = str(furl(settings.DARS_API_ROOT) / api_url)

    request_body = {
        field_name: st.session_state.get(field_name)
        for field_name, field in request_model.__fields__.items()
        if field.required
    }

    st.write("### CURL request")

    st.write(
        rf"""```
curl -X 'POST' \
  {shlex.quote(api_url)} \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d {shlex.quote(json.dumps(request_body, indent=2))}
```"""
    )

    if st.button("Call API 🚀"):
        with st.spinner("Waiting for API..."):
            r = requests.post(api_url, json=request_body)
            "### Response"
            r.raise_for_status()
            st.write(r.json())
