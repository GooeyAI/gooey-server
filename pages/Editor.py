import secrets
import typing
from copy import deepcopy

import streamlit as st
import streamlit.components.v1 as components
from google.cloud import firestore

from daras_ai.core import STEPS_REPO


def get_or_create_doc_id():
    query_params = st.experimental_get_query_params()
    doc_id = query_params.get("id", [new_doc_id()])[0]
    st.experimental_set_query_params(id=doc_id)
    return doc_id


def new_doc_id():
    return secrets.token_urlsafe(8)


@st.cache(allow_output_mutation=True)
def get_firestore_doc(doc_id: str):
    db_collection = get_db_collection()
    doc_ref = db_collection.document(doc_id)

    doc = doc_ref.get()
    if not doc.exists:
        doc_ref.create({"http_request_method": "GET"})
        doc = doc_ref.get()

    return doc.to_dict()


def get_db_collection():
    db = firestore.Client()
    db_collection = db.collection("daras-ai--political_example")
    return db_collection


def fork_me():
    db_collection = get_db_collection()

    fork_doc_id = new_doc_id()
    fork_doc_ref = db_collection.document(fork_doc_id)
    fork_doc_ref.set(deepcopy(st.session_state.to_dict()))

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


def save_me():
    db_collection = get_db_collection()

    doc_ref = db_collection.document(doc_id)
    doc_ref.set(deepcopy(st.session_state.to_dict()))

    cached_state.clear()
    cached_state.update(deepcopy(st.session_state.to_dict()))


def action_buttons():
    top_col1, top_col2 = st.columns(2)
    with top_col1:
        st.button("Fork Me 🍴", on_click=fork_me)
    with top_col2:
        st.button("Save Me 💾", on_click=save_me)


def render_steps(*, key: str, title: str):
    st.session_state.setdefault(key, [])
    state_steps = st.session_state[key]

    def call_step(idx: int, state: dict, fn: typing.Callable):
        def delete():
            state_steps.pop(idx)
            st.experimental_rerun()

        st.session_state.setdefault("variables", {})
        variables = st.session_state["variables"]
        for k in list(variables.keys()):
            if not k:
                variables.pop(k)
        fn(
            variables=variables,
            state=state,
            delete=delete,
            idx=idx,
        )

    selectbox_col, add_btn_col = st.columns(2)
    repo_to_use = STEPS_REPO[key]
    with selectbox_col:
        selected_fn = st.selectbox(
            title,
            [""] + [value for value in repo_to_use.values() if value.verbose_name],
            format_func=lambda fn: fn and fn.verbose_name,
        )
    with add_btn_col:
        add_step = st.button(f"Add", help=f"Add {key}")

    if selected_fn and add_step:
        state_steps.append({"name": selected_fn.__name__})
        st.experimental_rerun()

    for idx, step in enumerate(state_steps):
        try:
            step_fn = repo_to_use[step["name"]]
        except KeyError:
            continue
        call_step(idx, step, step_fn)


#
# main
#

st.set_page_config(layout="wide")

doc_id = get_or_create_doc_id()
cached_state = get_firestore_doc(doc_id)

if not st.session_state:
    st.session_state.update(deepcopy(cached_state))

action_buttons()


title = st.text_input("Title", key="header_title")
description = st.text_area("Description", key="header_desc")

col1, col2 = st.columns(2)

with col1:
    st.write("# Input")
    render_steps(key="input_steps", title="Add an input")

    st.write("# Recipie")
    render_steps(key="compute_steps", title="Add a step")

with col2:
    st.write("# Output")
    st.button("Run")
    render_steps(key="output_steps", title="Add an output")
