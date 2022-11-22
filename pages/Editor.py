import json
import secrets
import shlex
import typing
from copy import deepcopy
from time import time

import requests
import streamlit as st
import streamlit.components.v1 as components
from google.cloud import firestore

from daras_ai.computer import run_compute_steps
from daras_ai.core import STEPS_REPO, IO_REPO
from daras_ai.db import list_all_docs
from daras_ai.init import init_scripts
from daras_ai.secret_key_checker import check_secret_key
from daras_ai_v2 import settings
from daras_ai_v2.query_params import gooey_set_query_parm


def get_or_create_doc_id():
    query_params = st.experimental_get_query_params()
    doc_id = query_params.get("id", [new_doc_id()])[0]
    gooey_set_query_parm(id=doc_id)
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
    fork_state = deepcopy(st.session_state.to_dict())
    fork_state["header_title"] = f"Copy of {fork_state.get('header_title', '')}"
    fork_state["header_is_hidden"] = True
    fork_doc_ref.set(fork_state)
    list_all_docs()  # refresh list of docs

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

    doc_ref = db_collection.document(recipe_id)
    doc_ref.set(deepcopy(st.session_state.to_dict()))
    list_all_docs()  # refresh list of docs

    cached_state.clear()
    cached_state.update(deepcopy(st.session_state.to_dict()))


def action_buttons():
    top_col1, top_col2, top_col3 = st.columns(3)
    with top_col1:
        st.button("Save Me 💾", on_click=save_me)
    with top_col2:
        st.button("Save a Copy 📕", on_click=fork_me)
    st.checkbox("Is Hidden?", key="header_is_hidden")


def render_steps(*, key: str, title: str):
    state_steps = st.session_state[key]

    def call_step(idx: int, state: dict, fn: typing.Callable):
        for k in list(variables.keys()):
            if not k:
                variables.pop(k)
        fn(
            steps=state_steps,
            variables=variables,
            state=state,
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


def render_io_steps(key):
    for idx, step in enumerate(st.session_state[key]):
        try:
            step_fn = IO_REPO[step["name"]]
        except KeyError:
            continue
        step_fn(idx=idx, state=step, variables=variables)


#
# main
#

init_scripts()

recipe_id = get_or_create_doc_id()
cached_state = get_firestore_doc(recipe_id)

if "input_steps" not in st.session_state:
    st.session_state.update(deepcopy(cached_state))

st.session_state.setdefault("input_steps", [])
st.session_state.setdefault("compute_steps", [])
st.session_state.setdefault("output_steps", [])

st.session_state.setdefault("variables", {})
variables = st.session_state["variables"]


tab1, tab2, tab3 = st.tabs(["Run Recipe 🏃‍♂️", "Edit Recipe ✍️", "Run as API 🚀"])

with tab2:
    if check_secret_key("save this recipie"):
        action_buttons()

    st.text_input("Title", key="header_title")
    st.text_input("Tagline", key="header_tagline")
    st.text_area("Description", key="header_desc")

    col1, col2 = st.columns(2)

    with col1:
        st.write("### Inputs")
        render_steps(key="input_steps", title="Add an input")
    with col2:
        st.write("### Outputs")
        render_steps(key="output_steps", title="Add an output")

    st.write("### Steps")
    render_steps(key="compute_steps", title="Add a step")

with tab3:
    if check_secret_key("run as API"):
        api_url = f"{settings.API_BASE_URL}/v1/run-recipe/"
        params = {
            "recipe_id": recipe_id,
            "inputs": {
                input_step["var_name"]: variables.get(input_step["var_name"], "")
                for input_step in st.session_state["input_steps"]
            },
        }

        st.write(
            rf"""
            Call this recipe as an API 
    
```
curl -X 'POST' \
  {shlex.quote(api_url)} \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d {shlex.quote(json.dumps(params, indent=2))}
```
                """
        )

        if st.button("Call API 🚀"):
            with st.spinner("Waiting for API..."):
                r = requests.post(api_url, json=params)
                "Response"
                r.raise_for_status()
                st.write(r.json())

with tab1:
    col1, col2 = st.columns(2)

    with col1:
        st.write("## " + st.session_state.get("header_title", ""))
        tagline = st.session_state.get("header_tagline", "")
        if tagline:
            st.write("*" + tagline + "*")
        st.write(st.session_state.get("header_desc", ""))

        st.write("### Input")
        render_io_steps("input_steps")

    with col2:
        if st.button("Run Recipe 🏃‍♂️"):
            with st.spinner("Running Recipe..."):
                start = time()
                run_compute_steps(st.session_state["compute_steps"], variables)
                time_taken = time() - start
            st.caption(f"**Run Time** `{time_taken:.1f}` seconds. ")

        st.write("### Output")
        render_io_steps("output_steps")
