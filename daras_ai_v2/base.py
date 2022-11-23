import inspect
import json
import secrets
import shlex
import traceback
import typing
from copy import deepcopy
from time import time

import requests
import streamlit as st
from furl import furl
from google.cloud import firestore
from pydantic import BaseModel
from streamlit.components.v1 import html

from daras_ai.init import init_scripts
from daras_ai.secret_key_checker import check_secret_key
from daras_ai_v2 import settings
from daras_ai_v2.hidden_html_widget import hidden_html_js

DEFAULT_STATUS = "Running..."


class BasePage:
    title: str
    slug: str
    version: int = 1
    RequestModel: typing.Type[BaseModel]
    ResponseModel: typing.Type[BaseModel]

    @property
    def doc_name(self) -> str:
        # for backwards compat
        if self.version == 1:
            return self.slug
        return f"{self.slug}#{self.version}"

    @property
    def endpoint(self) -> str:
        return f"/v1/{self.slug}/run"

    def render(self):
        init_scripts()

        st.write("## " + self.title)
        run_tab, settings_tab, examples_tab, api_tab = st.tabs(
            ["🏃‍♀️Run", "⚙️ Settings", "🔖 Examples", "🚀 Run as API"]
        )

        if not st.session_state.get("__loaded__"):
            with st.spinner("Loading Settings..."):
                query_params = st.experimental_get_query_params()
                if "example_id" in query_params:
                    st.session_state.update(
                        get_saved_doc(
                            get_doc_ref(
                                self.doc_name,
                                sub_collection_id="examples",
                                sub_document_id=query_params["example_id"][0],
                            )
                        )
                    )
                else:
                    st.session_state.update(self.get_doc())

            with st.spinner("Loading Examples..."):
                st.session_state["__example_docs"] = list_all_docs(
                    document_id=self.doc_name,
                    sub_collection_id="examples",
                )

            st.session_state["__loaded__"] = True

        with settings_tab:
            self.render_settings()

        with examples_tab:
            self._examples_tab()

        with api_tab:
            run_as_api_tab(self.endpoint, self.RequestModel)

        with run_tab:
            col1, col2 = st.columns(2)

            with col1:
                submitted = self.render_form()
                self.render_description()

            with col2:
                self._runner(submitted)
                self.save_buttons()
        #
        # NOTE: Beware of putting code after runner since it will call experimental_rerun
        #

    def get_doc(self):
        return deepcopy(get_saved_doc(get_doc_ref(self.doc_name)))

    def render_description(self):
        pass

    def render_settings(self):
        pass

    def render_output(self):
        self.render_example(st.session_state)

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
                traceback.print_exc()
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
                        f"Success! Run Time: `{time_taken:.2f}` seconds. ",
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
        allow_delete = check_secret_key("delete example")

        for snapshot in st.session_state.get("__example_docs", []):
            example_id = snapshot.id
            doc = snapshot.to_dict()

            url = (
                furl(
                    settings.APP_BASE_URL,
                    query_params={"example_id": example_id},
                )
                / self.slug
            ).url

            col1, col2, col3, *_ = st.columns(6)

            with col1:
                st.markdown(
                    """
                    <div style="padding-bottom:8px">
                        <a target="_top"  style="color:white; text-decoration:none" class="btn"  href='%s'>
                          ✏️ Tweak 
                       </a>
                   </div>
                   <style>
                       .btn {
                       padding:8px;
                            display: inline-flex;
                            -webkit-box-align: center;
                            align-items: center;
                            -webkit-box-pack: center;
                            justify-content: center;
                            font-weight: 400;
                            padding: 0.25rem 0.75rem;
                            border-radius: 0.25rem;
                            margin: 0px;
                            line-height: 1.6;
                            color: inherit;
                            user-select: none;
                            background-color: rgb(8, 8, 8);
                            border: 1px solid rgba(255, 255, 255, 0.2);
                        }
                   </style>
                    """
                    % (url,),
                    unsafe_allow_html=True,
                )

            with col2:
                html(
                    """
                   <script src="https://cdn.jsdelivr.net/npm/clipboard@2.0.10/dist/clipboard.min.js"></script>
                    <script>
                       window.addEventListener("load", function (event) {
                        var clipboard = new ClipboardJS('.btn');
                        clipboard.on('success', function(e) {
                            alert("✅ Recipe example URL Copied");
                            });
                        });
                    </script>
                        <button style="color:white" class="btn" data-clipboard-text="%s" >
                           📎 Copy URL 
                       </button>
                    
                   <style>
                       .btn {
                            display: inline-flex;
                            -webkit-box-align: center;
                            align-items: center;
                            -webkit-box-pack: center;
                            justify-content: center;
                            font-weight: 400;
                            padding: 0.25rem 0.75rem;
                            border-radius: 0.25rem;
                            margin: 0px;
                            line-height: 1.6;
                            color: inherit;
                            width: auto;
                            user-select: none;
                            background-color: rgb(8, 8, 8);
                            border: 1px solid rgba(255, 255, 255, 0.2);
                        }
                   </style>
                    """
                    % url,
                    height=40,
                )

            with col3:
                if allow_delete:
                    pressed_delete = st.button(
                        "🗑️ Delete",
                        help=f"Delete example",
                        key=f"delete-{example_id}",
                    )
                    if pressed_delete:
                        example = get_doc_ref(
                            self.doc_name,
                            sub_collection_id="examples",
                            sub_document_id=example_id,
                        )
                        with st.spinner("deleting..."):
                            deleted = example.delete()
                            if deleted:
                                st.success("Deleted", icon="✅")

            self.render_example(doc)

            st.write("---")

    def render_example(self, state: dict):
        pass

    def preview_description(self) -> str:
        pass

    def preview_image(self, state: dict) -> str:
        pass


def set_saved_doc(
    doc_ref: firestore.DocumentReference,
    updated_state: dict,
):
    doc_ref.set(updated_state)
    # saved_state = get_saved_doc(doc_ref)
    # saved_state.clear()
    # saved_state.update(updated_state)


# @st.progress
# @st.cache(
#     allow_output_mutation=True,
#     show_spinner=False,
#     hash_funcs={
#         firestore.DocumentReference: lambda doc_ref: doc_ref.path,
#     },
# )
def get_saved_doc(doc_ref: firestore.DocumentReference) -> dict:
    return get_saved_doc_nocahe(doc_ref)


def get_saved_doc_nocahe(doc_ref):
    doc = doc_ref.get()
    if not doc.exists:
        doc_ref.create({})
        doc = doc_ref.get()
    return doc.to_dict()


# @cache_and_refresh
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
    if not check_secret_key("run as API", settings.API_SECRET_KEY):
        return

    api_docs_url = str(furl(settings.API_BASE_URL) / "docs")
    api_url = str(furl(settings.API_BASE_URL) / endpoint)

    request_body = get_example_request_body(request_model, st.session_state)

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


def get_example_request_body(
    request_model: typing.Type[BaseModel], state: dict
) -> dict:
    return {
        field_name: state.get(field_name)
        for field_name, field in request_model.__fields__.items()
        if field.required
    }
