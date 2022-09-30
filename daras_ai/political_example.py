import secrets
from copy import deepcopy

import streamlit as st
import streamlit.components.v1 as components
from google.cloud import firestore

from daras_ai.components.core import REPO

from daras_ai.components import text_api_selection
from daras_ai.components import http_data_source
from daras_ai.components import language_model_prompt_gen
from daras_ai.components import text_input
from daras_ai.components import train_data_formatter
from daras_ai.components.header import header
from daras_ai import settings
from daras_ai.components.text_input import raw_text_input
from daras_ai.components.text_output import raw_text_output

st.set_page_config(layout="wide")

query_params = st.experimental_get_query_params()
doc_id = query_params.get("id", [secrets.token_urlsafe(8)])[0]
st.experimental_set_query_params(id=doc_id)

db = firestore.Client()
db_collection = db.collection("daras-ai--political_example")
doc_ref = db_collection.document(doc_id)
st.session_state["doc_ref"] = doc_ref

doc = doc_ref.get()
if not doc.exists:
    doc_ref.create({"http_request_method": "GET"})
    doc = doc_ref.get()

st.session_state.update(doc.to_dict())

VARS = {}

fork_me = st.button("Fork Me 🍴")
if fork_me:
    fork_doc_id = secrets.token_urlsafe(8)

    fork_doc_ref = db_collection.document(fork_doc_id)
    fork_doc_ref.set(st.session_state.to_dict())

    components.html(
        f"""
        <script>
        let new_url = window.top.location.href.split("?")[0] + "?id={fork_doc_id}";
        window.open(new_url, "_blank");
        </script>
        """,
        width=0,
        height=0,
    )


def call_step(idx: int, state: dict):
    step_name: str = state["name"]

    def set_state(update: dict):
        old = deepcopy(state)
        state.update(update)
        if state == old:
            return
        doc_ref.update(st.session_state.to_dict())

    def delete():
        st.session_state["steps"].pop(idx)
        doc_ref.update(st.session_state.to_dict())
        st.experimental_rerun()

    fn = REPO[step_name]
    fn(variables=VARS, state=state, set_state=set_state, delete=delete, idx=idx)


st.session_state.setdefault("header", {"name": header.__name__})
call_step(0, st.session_state["header"])

col1, col2 = st.columns(2)

with col1:
    st.write("## Input")

    st.session_state.setdefault("input_step", {"name": raw_text_input.__name__})
    call_step(0, st.session_state["input_step"])

    st.write("## Steps")

    st.session_state.setdefault("steps", [])
    for idx, step in enumerate(st.session_state["steps"]):
        call_step(idx, step)

with col2:
    st.write("## Output")

    st.button("Run")

    st.session_state.setdefault("output_step", {"name": raw_text_output.__name__})
    call_step(0, st.session_state["output_step"])

col1, col2, *_ = st.columns(5)
with col1:
    fn = st.selectbox(
        "Add a step",
        [value for value in REPO.values() if value.verbose_name],
        format_func=lambda fn: fn.verbose_name,
    )
with col2:
    btn = st.button("Add")

if btn:
    st.session_state["steps"].append({"name": fn.__name__})
    doc_ref.update(st.session_state.to_dict())
    st.experimental_rerun()
