import inspect
import json
import secrets
import shlex
import typing
from copy import deepcopy
from time import time

import requests
import streamlit as st
from furl import furl
from google.cloud import firestore
from pydantic import BaseModel

from daras_ai.cache_tools import cache_and_refresh
from daras_ai.secret_key_checker import check_secret_key
from daras_ai_v2 import settings

DEFAULT_STATUS = "Running Recipe..."


class BasePage:
    title: str
    doc_name: str
    endpoint: str
    RequestModel: typing.Type[BaseModel]
    ResponseModel: typing.Type[BaseModel]

    def render(self):
        st.set_page_config(page_title=self.title + " - Gooey.AI")

        logo()
        st.write("## " + self.title)
        run_tab, settings_tab, examples_tab, api_tab = st.tabs(
            ["🏃‍♀️Run", "⚙️ Settings", "🔖 Examples", "🚀 Run as API"]
        )

        if not st.session_state.get("__loaded__"):
            with st.spinner("Loading Settings..."):
                st.session_state.update(
                    deepcopy(get_saved_doc(get_doc_ref(self.doc_name)))
                )
            st.session_state["__loaded__"] = True

        with settings_tab:
            self.render_settings()

        with examples_tab:
            self._examples_tab()

        with api_tab:
            run_as_api_tab(self.endpoint, self.RequestModel)

        with run_tab:
            self.render_description()
            submitted = self.render_form()
            self._runner(submitted)
            self.save_buttons()
        #
        # NOTE: Beware of putting code after runner since it will call experimental_rerun
        #

    def render_description(self):
        pass

    def render_settings(self):
        pass

    def render_output(self):
        pass

    def render_form(self) -> bool:
        return False

    def run(self, state: dict) -> typing.Iterator[str | None]:
        raise NotImplemented

    def _runner(self, submitted: bool):
        assert inspect.isgeneratorfunction(self.run)

        # The area for displaying status messages streamed from run()
        status_area = st.empty()

        output_area = st.empty()
        with output_area.container():
            self.render_output()

        if submitted:
            st.session_state["__status"] = DEFAULT_STATUS
            st.session_state["__gen"] = self.run(st.session_state)
            st.session_state["__time_taken"] = 0

            self.clear_outputs()

        gen = st.session_state.get("__gen")
        start_time = None

        if gen:
            try:
                with status_area, st.spinner(st.session_state["__status"]):
                    start_time = time()
                    # advance the generator (to further progress of run())
                    st.session_state["__status"] = next(gen) or DEFAULT_STATUS
                    # increment total time taken after every iteration
                    st.session_state["__time_taken"] += time() - start_time

            except StopIteration:
                # Weird but important! This measures the runtime of code after the last `yield` in `run()`
                if start_time:
                    st.session_state["__time_taken"] += time() - start_time

                # save a snapshot of the params used to create this output
                st.session_state["__state_to_save"] = {
                    field_name: deepcopy(st.session_state[field_name])
                    for field_name in self.fields_to_save()
                    if field_name in st.session_state
                }

                # cleanup is important!
                del st.session_state["__status"]
                del st.session_state["__gen"]

            # render ValueError nicely
            except Exception as e:
                with status_area:
                    st.error(f"{type(e).__name__} - {e}", icon="⚠️")
                # cleanup is important!
                del st.session_state["__status"]
                del st.session_state["__gen"]
                del st.session_state["__time_taken"]
                return

            # this bit of hack streams the outputs from run() in realtime
            st.experimental_rerun()

        else:
            time_taken = st.session_state.get("__time_taken", 0)
            if time_taken:
                with status_area:
                    st.success(
                        f"Success! Run Time: `{time_taken:.2f}` seconds. "
                        f"This GPU time is free while we're building daras.ai, Enjoy!",
                        icon="✅",
                    )
                    del st.session_state["__time_taken"]

    def clear_outputs(self):
        for field_name in self.ResponseModel.__fields__:
            try:
                del st.session_state[field_name]
            except KeyError:
                pass

    def save_buttons(self):
        state_to_save = st.session_state.get("__state_to_save")
        if not state_to_save:
            return

        if not check_secret_key("Save"):
            return

        col1, col2, *_ = st.columns(3)
        pressed_save = col1.button("🔖 Add as Example")
        pressed_star = col2.button("💾 Save to Recipe & Settings")

        if pressed_save:
            sub_collection = "examples"
            sub_doc = secrets.token_urlsafe(8)
        elif pressed_star:
            sub_collection = None
            sub_doc = None
        else:
            return

        with st.spinner("Saving..."):
            set_saved_doc(
                get_doc_ref(
                    self.doc_name,
                    sub_collection_id=sub_collection,
                    sub_document_id=sub_doc,
                ),
                state_to_save,
            )

        st.success("Done", icon="✅")

    def fields_to_save(self) -> [str]:
        # only save the fields in request/response
        return [
            field_name
            for model in (self.RequestModel, self.ResponseModel)
            for field_name in model.__fields__
        ]

    def _examples_tab(self):
        for snapshot in list_all_docs(
            document_id=self.doc_name,
            sub_collection_id="examples",
        ):
            example_id = snapshot.id
            doc = snapshot.to_dict()

            col1, col2, col3, *_ = st.columns(6)
            with col1:
                pressed_tweak = st.button("✏️ Tweak", help=f"tweak {example_id}")
            with col2:
                pressed_delete = st.button("🗑️ Delete", help=f"delete {example_id}")
            with col3:
                pressed_share = st.button("✉️️ Share", help=f"delete {example_id}")

            self.render_example(doc)

            st.write("---")

    def render_example(self, state: dict):
        pass


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
            <img width=150 src="https://storage.googleapis.com/dara-c1b52.appspot.com/gooey/gooey-logo-rect.png"></img>
        </a>
        <span style="position: absolute; right: 0px">
            <a href="https://dara.network/privacy/">Privacy</a> & 
            <a href="https://dara.network/terms/">Terms</a>
        </span>
        """,
        unsafe_allow_html=True,
    )
    st.write("")


def set_saved_doc(
    doc_ref: firestore.DocumentReference,
    updated_state: dict,
):
    doc_ref.set(updated_state)
    saved_state = get_saved_doc(doc_ref)
    saved_state.clear()
    saved_state.update(updated_state)


@st.cache(
    allow_output_mutation=True,
    show_spinner=False,
    hash_funcs={
        firestore.DocumentReference: lambda doc_ref: doc_ref.path,
    },
)
def get_saved_doc(doc_ref: firestore.DocumentReference) -> dict:
    return get_saved_doc_nocahe(doc_ref)


def get_saved_doc_nocahe(doc_ref):
    doc = doc_ref.get()
    if not doc.exists:
        doc_ref.create({})
        doc = doc_ref.get()
    return doc.to_dict()


@cache_and_refresh
def list_all_docs(
    collection_id="daras-ai-v2",
    *,
    document_id: str = None,
    sub_collection_id: str = None,
):
    db = firestore.Client()
    db_collection = db.collection(collection_id)
    if sub_collection_id:
        doc_ref = db_collection.document(document_id)
        db_collection = doc_ref.collection(sub_collection_id)
    return db_collection.get()


def get_doc_ref(
    document_id: str,
    *,
    collection_id="daras-ai-v2",
    sub_collection_id: str = None,
    sub_document_id: str = None,
):
    db = firestore.Client()
    db_collection = db.collection(collection_id)
    doc_ref = db_collection.document(document_id)
    if sub_collection_id:
        sub_collection = doc_ref.collection(sub_collection_id)
        doc_ref = sub_collection.document(sub_document_id)
    return doc_ref


def run_as_api_tab(endpoint: str, request_model: typing.Type[BaseModel]):
    if not check_secret_key("run as API"):
        return

    api_docs_url = str(furl(settings.DARS_API_ROOT) / "docs")
    api_url = str(furl(settings.DARS_API_ROOT) / endpoint)

    request_body = {
        field_name: st.session_state.get(field_name)
        for field_name, field in request_model.__fields__.items()
        if field.required
    }

    st.markdown(
        f"""<a href="{api_docs_url}">API Docs</a>""",
        unsafe_allow_html=True,
    )

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
