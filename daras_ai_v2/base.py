import inspect
import json
import random
import shlex
import string
import traceback
import typing
from copy import deepcopy
from time import time

import requests
import streamlit as st
from firebase_admin import auth
from firebase_admin.auth import UserRecord
from furl import furl
from google.cloud import firestore
from pydantic import BaseModel

from daras_ai.init import init_scripts
from daras_ai.secret_key_checker import check_secret_key
from daras_ai_v2 import settings
from daras_ai_v2.copy_to_clipboard_button_widget import (
    copy_to_clipboard_button,
)
from daras_ai_v2.html_spinner_widget import html_spinner
from daras_ai_v2.query_params import gooey_reset_query_parm
from daras_ai_v2.send_email import send_email_via_postmark
from daras_ai_v2.utils import email_support_about_reported_run

DEFAULT_STATUS = "Running..."

DEFAULT_COLLECTION = "daras-ai-v2"

EXAMPLES_COLLECTION = "examples"
USER_RUNS_COLLECTION = "user_runs"

EXAMPLE_ID_QUERY_PARAM = "example_id"
RUN_ID_QUERY_PARAM = "run_id"
USER_ID_QUERY_PARAM = "uid"


class BasePage:
    title: str
    slug: str
    version: int = 1
    sane_defaults: dict = {}
    RequestModel: typing.Type[BaseModel]
    ResponseModel: typing.Type[BaseModel]

    @property
    def doc_name(self) -> str:
        # for backwards compat
        if self.version == 1:
            return self.slug
        return f"{self.slug}#{self.version}"

    @classmethod
    def app_url(cls) -> str:
        return str(furl(settings.APP_BASE_URL) / cls.slug)

    @property
    def endpoint(self) -> str:
        return f"/v1/{self.slug}/run"

    def render(self):
        init_scripts()

        st.write("## " + self.title)
        run_tab, settings_tab, examples_tab, api_tab = st.tabs(
            ["🏃‍♀️Run", "⚙️ Settings", "🔖 Examples", "🚀 Run as API"]
        )

        self._load_session_state()

        with settings_tab:
            self.render_settings()

        with examples_tab:
            self._examples_tab()

        with api_tab:
            run_as_api_tab(self.endpoint, self.RequestModel)

        with run_tab:
            col1, col2 = st.columns(2)

            self.render_footer()

            with col1:
                submitted = self.render_form()
                self.render_description()

            with col2:
                self._runner(submitted)
        #
        # NOTE: Beware of putting code here since runner will call experimental_rerun
        #

    def _load_session_state(self):
        if st.session_state.get("__loaded__"):
            return

        with st.spinner("Loading Settings..."):
            query_params = st.experimental_get_query_params()
            state = self.get_doc_from_query_params(query_params)

            if state is None:
                st.write("### 404: We can't find this page!")
                st.stop()

            st.session_state.update(state)

        with st.spinner("Loading Examples..."):
            st.session_state["__example_docs"] = list_all_docs(
                document_id=self.doc_name,
                sub_collection_id=EXAMPLES_COLLECTION,
            )

        for k, v in self.sane_defaults.items():
            st.session_state.setdefault(k, v)

        st.session_state["__loaded__"] = True

    def extract_query_params(self, query_params):
        example_id = query_params.get(EXAMPLE_ID_QUERY_PARAM)
        run_id = query_params.get(RUN_ID_QUERY_PARAM)
        uid = query_params.get(USER_ID_QUERY_PARAM)
        if isinstance(example_id, list):
            example_id = example_id[0]
        if isinstance(run_id, list):
            run_id = run_id[0]
        if isinstance(uid, list):
            uid = uid[0]
        return example_id, run_id, uid

    def get_doc_from_query_params(self, query_params) -> dict | None:
        example_id, run_id, uid = self.extract_query_params(query_params)
        return self.get_firestore_state(example_id, run_id, uid)

    def get_firestore_state(self, example_id, run_id, uid):
        if example_id:
            snapshot = self._example_doc_ref(example_id).get()
        elif run_id:
            snapshot = self._run_doc_ref(run_id, uid).get()
        else:
            snapshot = self.get_recipe_doc()
        return snapshot.to_dict()

    def get_recipe_doc(self) -> firestore.DocumentSnapshot:
        return get_or_create_doc(self._recipe_doc_ref())

    def _recipe_doc_ref(self) -> firestore.DocumentReference:
        return get_doc_ref(self.doc_name)

    def _run_doc_ref(self, run_id: str, uid: str) -> firestore.DocumentReference:
        return get_doc_ref(
            collection_id=USER_RUNS_COLLECTION,
            document_id=uid,
            sub_collection_id=self.doc_name,
            sub_document_id=run_id,
        )

    def _example_doc_ref(self, example_id: str) -> firestore.DocumentReference:
        return get_doc_ref(
            sub_collection_id=EXAMPLES_COLLECTION,
            document_id=self.doc_name,
            sub_document_id=example_id,
        )

    def render_description(self):
        pass

    def render_settings(self):
        pass

    def render_output(self):
        self.render_example(st.session_state)

    def render_form_v2(self):
        pass

    def validate_form_v2(self) -> bool:
        pass

    def render_form(self) -> bool:
        with st.form(f"{self.slug}Form"):
            self.render_form_v2()
            submitted = st.form_submit_button("🏃‍ Submit")

        if not submitted:
            return False

        try:
            self.validate_form_v2()
        except AssertionError:
            st.error("Please provide a Prompt and an Email Address", icon="⚠️")
            return False
        else:
            return True

    def render_footer(self):
        pass

    def run(self, state: dict) -> typing.Iterator[str | None]:
        raise NotImplemented

    def _render_before_output(self):
        query_params = st.experimental_get_query_params()
        example_id, run_id, uid = self.extract_query_params(query_params)
        url = str(furl(self.app_url(), query_params=query_params))
        current_user: UserRecord = st.session_state.get("_current_user")

        if example_id:
            query_params = dict(example_id=example_id)
        elif run_id and uid:
            query_params = dict(run_id=run_id, uid=uid)
            # ONLY RUNS CAN BE REPORTED
            reported = st.button("❗Report")
            if reported:
                with st.spinner("Reporting..."):
                    self.flag_run(run_id=run_id, uid=uid)
                    email_support_about_reported_run(
                        run_id=run_id, uid=uid, url=url, email=current_user.email
                    )
                    st.success("Reported. Reload the page to see changes")
        else:
            return

        col1, col2 = st.columns([3, 1])

        with col1:
            st.text_input(
                "recipe url",
                label_visibility="collapsed",
                disabled=True,
                value=url,
            )

        with col2:
            copy_to_clipboard_button(
                "📎 Copy URL",
                value=url,
                style="padding: 6px",
                height=55,
            )

    def flag_run(self, run_id: str, uid: str):
        ref = self._run_doc_ref(uid=uid, run_id=run_id)
        ref.set({"is_flagged": True}, merge=True)

    def save_run(self):
        current_user: auth.UserRecord = st.session_state.get("_current_user")
        if not current_user:
            return

        query_params = st.experimental_get_query_params()
        run_id = query_params.get(RUN_ID_QUERY_PARAM, [_random_str_id()])[0]
        gooey_reset_query_parm(run_id=run_id, uid=current_user.uid)

        run_doc_ref = self._run_doc_ref(run_id, current_user.uid)
        state_to_save = self._get_state_to_save()

        run_doc_ref.set(state_to_save)

    def _runner(self, submitted: bool):
        assert inspect.isgeneratorfunction(self.run)

        # The area for displaying status messages streamed from run()
        status_area = st.empty()
        # output area
        before_output = st.empty()
        output_area = st.empty()
        after_output = st.empty()

        if "__status" in st.session_state:
            with status_area:
                html_spinner(st.session_state["__status"])

        if submitted:
            st.session_state["__status"] = DEFAULT_STATUS
            st.session_state["__gen"] = self.run(st.session_state)
            st.session_state["__time_taken"] = 0

            with status_area:
                html_spinner("Starting...")

            self.clear_outputs()
            self.save_run()

        gen = st.session_state.get("__gen")
        start_time = None

        with output_area.container():
            self.render_output()

        # only render if not running
        if not gen:
            with before_output.container():
                self._render_before_output()
            with after_output.container():
                self._render_after_output()

        if gen:
            try:
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
                st.session_state["__state_to_save"] = self._get_state_to_save()

                # cleanup is important!
                del st.session_state["__status"]
                del st.session_state["__gen"]

            # render errors nicely
            except Exception as e:
                traceback.print_exc()
                with status_area:
                    st.error(f"{type(e).__name__} - {err_msg_for_exc(e)}", icon="⚠️")
                # cleanup is important!
                del st.session_state["__status"]
                del st.session_state["__gen"]
                del st.session_state["__time_taken"]
                return

            # save after every step
            self.save_run()

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
        gooey_reset_query_parm()

    def _render_after_output(self):
        state_to_save = (
            st.session_state.get("__state_to_save") or self._get_state_to_save()
        )
        if not state_to_save:
            return

        if not check_secret_key("Save"):
            return

        new_example_id = None
        doc_ref = None
        query_params = st.experimental_get_query_params()
        col1, col2 = st.columns(2)

        with col2:
            submitted_1 = st.button("🔖 Add as Example")
            if submitted_1:
                new_example_id = _random_str_id()
                doc_ref = self._example_doc_ref(new_example_id)

        with col1:
            if EXAMPLE_ID_QUERY_PARAM in query_params:
                submitted_2 = st.button("💾 Save This Example & Settings")
                if submitted_2:
                    example_id = query_params[EXAMPLE_ID_QUERY_PARAM][0]
                    doc_ref = self._example_doc_ref(example_id)
            else:
                submitted_3 = st.button("💾 Save This Recipe & Settings")
                if submitted_3:
                    doc_ref = get_doc_ref(self.doc_name)

        if not doc_ref:
            return

        with st.spinner("Saving..."):
            doc_ref.set(state_to_save)

            if new_example_id:
                gooey_reset_query_parm(example_id=new_example_id)
                st.session_state["__example_docs"].append(doc_ref.get())
                st.experimental_rerun()

        st.success("Done", icon="✅")

    def _get_state_to_save(self):
        return {
            field_name: deepcopy(st.session_state[field_name])
            for field_name in self.fields_to_save()
            if field_name in st.session_state
        }

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

            url = str(
                furl(
                    self.app_url(),
                    query_params={EXAMPLE_ID_QUERY_PARAM: example_id},
                )
            )

            col1, col2, col3, *_ = st.columns(6)

            with col1:
                st.markdown(
                    f"""
                    <a target="_top" class="streamlit-like-btn" href="{url}">
                      ✏️ Tweak 
                    </a>
                    """,
                    unsafe_allow_html=True,
                )

            with col2:
                copy_to_clipboard_button("📎 Copy URL", value=url)

            with col3:
                if allow_delete:
                    self._example_delete_button(example_id)

            self.render_example(doc)

            st.write("---")

    def _example_delete_button(self, example_id):
        pressed_delete = st.button(
            "🗑️ Delete",
            help=f"Delete example",
            key=f"delete-{example_id}",
        )
        if not pressed_delete:
            return

        example = self._example_doc_ref(example_id)

        with st.spinner("deleting..."):
            deleted = example.delete()
            if not deleted:
                st.error("Failed")
                return

        example_docs = st.session_state["__example_docs"]
        for idx, snapshot in enumerate(example_docs):
            if snapshot.id == example_id:
                example_docs.pop(idx)
                st.experimental_rerun()

    def render_example(self, state: dict):
        pass

    def preview_description(self, state: dict) -> str:
        pass

    def preview_image(self, state: dict) -> str:
        pass


def get_doc_ref(
    document_id: str,
    *,
    collection_id=DEFAULT_COLLECTION,
    sub_collection_id: str = None,
    sub_document_id: str = None,
) -> firestore.DocumentReference:
    db = firestore.Client()
    db_collection = db.collection(collection_id)
    doc_ref = db_collection.document(document_id)
    if sub_collection_id:
        sub_collection = doc_ref.collection(sub_collection_id)
        doc_ref = sub_collection.document(sub_document_id)
    return doc_ref


def get_or_create_doc(
    doc_ref: firestore.DocumentReference,
) -> firestore.DocumentSnapshot:
    doc = doc_ref.get()
    if not doc.exists:
        doc_ref.create({})
        doc = doc_ref.get()
    return doc


def list_all_docs(
    collection_id=DEFAULT_COLLECTION,
    *,
    document_id: str = None,
    sub_collection_id: str = None,
) -> list:
    db = firestore.Client()
    db_collection = db.collection(collection_id)
    if sub_collection_id:
        doc_ref = db_collection.document(document_id)
        db_collection = doc_ref.collection(sub_collection_id)
    return db_collection.get()


def run_as_api_tab(endpoint: str, request_model: typing.Type[BaseModel]):

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
  -H 'Authorization: Token $GOOEY_API_KEY' \
  -d {shlex.quote(json.dumps(request_body, indent=2))}
```"""
    )

    if st.button("Call API 🚀"):
        with st.spinner("Waiting for API..."):
            r = requests.post(
                api_url,
                json=request_body,
                headers={"Authorization": f"Token {settings.API_SECRET_KEY}"},
            )
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


def err_msg_for_exc(e):
    if isinstance(e, requests.HTTPError):
        response: requests.Response = e.response
        try:
            err_body = response.json()
        except requests.JSONDecodeError:
            err_body = response.text
        err_msg = f"(HTTP {response.status_code}) {err_body}"
    else:
        err_msg = f"{type(e).__name__} - {e}"
    return err_msg


def _random_str_id(n=8):
    charset = string.ascii_lowercase + string.digits
    return "".join(random.choice(charset) for _ in range(n))
