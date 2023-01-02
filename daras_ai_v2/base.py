import datetime
import inspect
import traceback
import typing
import uuid
from copy import deepcopy
from time import time

import requests
import sentry_sdk
import streamlit as st
from firebase_admin import auth
from firebase_admin.auth import UserRecord
from furl import furl
from google.cloud import firestore
from pydantic import BaseModel
from pydantic.generics import GenericModel
from sentry_sdk.tracing import TRANSACTION_SOURCE_ROUTE

from daras_ai.init import init_scripts
from daras_ai.secret_key_checker import is_admin
from daras_ai_v2 import db
from daras_ai_v2 import settings
from daras_ai_v2.api_examples_widget import api_example_generator
from daras_ai_v2.copy_to_clipboard_button_widget import (
    copy_to_clipboard_button,
)
from daras_ai_v2.crypto import (
    get_random_doc_id,
)
from daras_ai_v2.db import get_user_doc_ref
from daras_ai_v2.html_spinner_widget import html_spinner
from daras_ai_v2.manage_api_keys_widget import manage_api_keys
from daras_ai_v2.query_params import gooey_reset_query_parm
from daras_ai_v2.utils import email_support_about_reported_run
from daras_ai_v2.utils import random

DEFAULT_STATUS = "Running..."

EXAMPLES_COLLECTION = "examples"
USER_RUNS_COLLECTION = "user_runs"

EXAMPLE_ID_QUERY_PARAM = "example_id"
RUN_ID_QUERY_PARAM = "run_id"
USER_ID_QUERY_PARAM = "uid"
GOOEY_LOGO = (
    "https://storage.googleapis.com/dara-c1b52.appspot.com/gooey/gooey_logo_300x142.png"
)

O = typing.TypeVar("O")


class ApiResponseModel(GenericModel, typing.Generic[O]):
    id: str
    url: str
    created_at: str
    output: O


class BasePage:
    title: str
    slug_versions: list[str]
    version: int = 1
    sane_defaults: dict = {}
    RequestModel: typing.Type[BaseModel]
    ResponseModel: typing.Type[BaseModel]

    price = settings.CREDITS_TO_DEDUCT_PER_RUN

    @property
    def doc_name(self) -> str:
        # for backwards compat
        if self.version == 1:
            return self.slug_versions[0]
        return f"{self.slug_versions[0]}#{self.version}"

    @classmethod
    def app_url(cls, example_id=None, run_id=None, uid=None) -> str:
        query_params = {}
        if example_id:
            query_params = dict(example_id=example_id)
        elif run_id and uid:
            query_params = dict(run_id=run_id, uid=uid)
        return str(
            furl(settings.APP_BASE_URL, query_params=query_params)
            / (cls.slug_versions[-1] + "/")
        )

    @property
    def endpoint(self) -> str:
        return f"/v2/{self.slug_versions[0]}/"

    def render(self):
        try:
            self._render()
        except Exception as e:
            sentry_sdk.capture_exception(e)
            raise

    def _render(self):
        with sentry_sdk.configure_scope() as scope:
            scope.set_extra("url", self.app_url())
            scope.set_extra("query_params", st.experimental_get_query_params())
            scope.set_transaction_name(
                "/" + self.slug_versions[0], source=TRANSACTION_SOURCE_ROUTE
            )

        init_scripts()

        st.write("## " + self.title)
        run_tab, settings_tab, examples_tab, api_tab = st.tabs(
            ["🏃‍♀️Run", "⚙️ Settings", "🔖 Examples", "🚀 Run as API"]
        )

        self._load_session_state()

        with run_tab:
            self._check_if_flagged()

            form_col, runner_col = st.columns(2)
            with form_col:
                submitted = self.render_form()

            self.render_step_row()
            self.render_footer()

        with settings_tab:
            self.render_settings()

        with examples_tab:
            self._examples_tab()

        with api_tab:
            self.run_as_api_tab()

        with runner_col:
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

        for k, v in self.sane_defaults.items():
            st.session_state.setdefault(k, v)

        st.session_state["__loaded__"] = True

    def _check_if_flagged(self):
        if not st.session_state.get("is_flagged"):
            return

        st.error("### This Content has been Flagged")

        if is_admin():
            unflag_pressed = st.button("UnFlag")
            if not unflag_pressed:
                return
            with st.spinner("Removing flag..."):
                query_params = st.experimental_get_query_params()
                example_id, run_id, uid = self.extract_query_params(query_params)
                if run_id and uid:
                    self.update_flag_for_run(run_id=run_id, uid=uid, is_flagged=False)
            st.success("Removed flag. Reload the page to see changes")
        else:
            st.write(
                "Our support team is reviewing this run. Please come back after some time."
            )
            # Return and Don't render the run any further
            st.stop()

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
            snapshot = self.run_doc_ref(run_id, uid).get()
        else:
            snapshot = self.get_recipe_doc()
        return snapshot.to_dict()

    def get_recipe_doc(self) -> firestore.DocumentSnapshot:
        return db.get_or_create_doc(self._recipe_doc_ref())

    def _recipe_doc_ref(self) -> firestore.DocumentReference:
        return db.get_doc_ref(self.doc_name)

    def run_doc_ref(self, run_id: str, uid: str) -> firestore.DocumentReference:
        return db.get_doc_ref(
            collection_id=USER_RUNS_COLLECTION,
            document_id=uid,
            sub_collection_id=self.doc_name,
            sub_document_id=run_id,
        )

    def _example_doc_ref(self, example_id: str) -> firestore.DocumentReference:
        return db.get_doc_ref(
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

    def validate_form_v2(self):
        pass

    def render_form(self) -> bool:
        with st.form(f"{self.slug_versions[0]}Form"):
            self.render_form_v2()

            col1, col2 = st.columns([2, 1])
            with col1:
                st.caption(
                    "_By submitting, you agree to Gooey.AI's [terms](https://gooey.ai/terms) & [privacy policy](https://gooey.ai/privacy)_",
                )
            with col2:
                submitted = st.form_submit_button("🏃 Submit", type="primary")

        if not submitted:
            return False

        try:
            self.validate_form_v2()
        except AssertionError as e:
            st.error(e, icon="⚠️")
            return False
        else:
            return True

    def render_step_row(self):
        with st.expander("**👣 Steps**"):
            col1, col2 = st.columns([1, 2])
            with col1:
                self.render_description()
            with col2:
                self.render_steps()

    def render_footer(self):
        col1, col2 = st.columns(2)
        with col1:
            placeholder = st.empty()
            try:
                self.render_usage_guide()
            except NotImplementedError:
                pass
            else:
                with placeholder:
                    st.write(
                        """
                        ## How to Use This Recipe
                        """
                    )

            with st.expander(
                "**🙋🏽‍♀️ Need more help? [Join our Discord](https://discord.gg/KQCrzgMPJ2)**",
                expanded=False,
            ):
                st.markdown(
                    """
                    <div style="position: relative; padding-bottom: 56.25%; height: 500px; max-width: 500px;">
                    <iframe src="https://e.widgetbot.io/channels/643360566970155029/1046049067337273444" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;"></iframe>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        with col2:
            pass
            # self._render_admin_options()

    def render_usage_guide(self):
        raise NotImplementedError

    def run(self, state: dict) -> typing.Iterator[str | None]:
        raise NotImplementedError

    def _render_report_button(self):
        current_user: UserRecord = st.session_state.get("_current_user")

        query_params = st.experimental_get_query_params()
        example_id, run_id, uid = self.extract_query_params(query_params)

        if not (current_user and run_id and uid):
            # ONLY RUNS CAN BE REPORTED
            return

        reported = st.button("❗Report")
        if not reported:
            return

        with st.spinner("Reporting..."):
            self.update_flag_for_run(run_id=run_id, uid=uid, is_flagged=True)
            email_support_about_reported_run(
                run_id=run_id,
                uid=uid,
                url=self._get_current_url(),
                email=current_user.email,
            )
            st.success("Reported. Reload the page to see changes")

    def _render_before_output(self):
        query_params = st.experimental_get_query_params()
        example_id, run_id, uid = self.extract_query_params(query_params)
        if not (run_id or example_id):
            return

        url = self._get_current_url()
        if not url:
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
                "🔗 Copy URL",
                value=url,
                style="padding: 6px",
                height=55,
            )

    def _get_current_url(self) -> str | None:
        query_params = st.experimental_get_query_params()
        example_id, run_id, uid = self.extract_query_params(query_params)
        return self.app_url(example_id, run_id, uid)

    def update_flag_for_run(self, run_id: str, uid: str, is_flagged: bool):
        ref = self.run_doc_ref(uid=uid, run_id=run_id)
        ref.update({"is_flagged": is_flagged})

    def save_run(self):
        current_user: auth.UserRecord = st.session_state.get("_current_user")
        if not current_user:
            return

        query_params = st.experimental_get_query_params()
        run_id = query_params.get(RUN_ID_QUERY_PARAM, [get_random_doc_id()])[0]
        gooey_reset_query_parm(run_id=run_id, uid=current_user.uid)

        run_doc_ref = self.run_doc_ref(run_id, current_user.uid)
        state_to_save = self.state_to_doc(st.session_state)
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

        if st.session_state.get("__randomize"):
            st.session_state["seed"] = int(random.randrange(4294967294))
            st.session_state.pop("__randomize", None)
            submitted = True

        if submitted:
            st.session_state["__status"] = DEFAULT_STATUS
            st.session_state["__gen"] = self.run(st.session_state)
            st.session_state["__time_taken"] = 0

            with status_area:
                html_spinner("Starting...")

            self._pre_run_checklist()

            if not self.check_credits():
                status_area.empty()
                return

        gen = st.session_state.get("__gen")
        start_time = None

        # render outputs
        with output_area.container():
            self.render_output()

        # render before/after output blocks if not running
        if not gen:
            with before_output.container():
                self._render_before_output()
            with after_output.container():
                self._render_after_output()

        if gen:  # if running...
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
                st.session_state["__state_to_save"] = self.state_to_doc(
                    st.session_state
                )

                # cleanup is important!
                del st.session_state["__status"]
                del st.session_state["__gen"]

                self.deduct_credits()

            # render errors nicely
            except Exception as e:
                sentry_sdk.capture_exception(e)
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

    def _pre_run_checklist(self):
        self._setup_rng_seed()
        self.clear_outputs()
        self.save_run()

    def _setup_rng_seed(self):
        seed = st.session_state.get("seed")
        if not seed:
            return
        random.seed(seed)

    def clear_outputs(self):
        for field_name in self.ResponseModel.__fields__:
            try:
                del st.session_state[field_name]
            except KeyError:
                pass
        gooey_reset_query_parm()

    def _render_after_output(self):
        if "seed" in self.RequestModel.schema_json():
            seed = st.session_state.get("seed")
            # st.write("is_admin" + str(is_admin()))
            col1, col2, col3 = st.columns(3)
            with col1:
                st.caption(f"*Seed: `{seed}`*")
            with col2:
                randomize = st.button("♻️ Regenerate")
                if randomize:
                    st.session_state["__randomize"] = True
                    st.experimental_rerun()
            with col3:
                self._render_report_button()
        else:
            self._render_report_button()

        self._render_admin_options()

    def _render_admin_options(self):
        state_to_save = st.session_state.get("__state_to_save") or self.state_to_doc(
            st.session_state
        )
        # st.write("state_to_save " + str(state_to_save))

        if not state_to_save:
            return

        if not is_admin():
            return

        new_example_id = None
        doc_ref = None
        query_params = st.experimental_get_query_params()

        with st.expander("🛠️ Admin Options"):
            col1, col2 = st.columns(2)
            with col2:
                submitted_1 = st.button("🔖 Add as Example")
                if submitted_1:
                    new_example_id = get_random_doc_id()
                    doc_ref = self._example_doc_ref(new_example_id)

            with col1:
                if EXAMPLE_ID_QUERY_PARAM in query_params:
                    submitted_2 = st.button("💾 Save Example & Settings")
                    if submitted_2:
                        example_id = query_params[EXAMPLE_ID_QUERY_PARAM][0]
                        doc_ref = self._example_doc_ref(example_id)
                else:
                    submitted_3 = st.button("💾 Save Workflow & Settings")
                    if submitted_3:
                        doc_ref = db.get_doc_ref(self.doc_name)

            if not doc_ref:
                return

            with st.spinner("Saving..."):
                doc_ref.set(state_to_save)

                if new_example_id:
                    gooey_reset_query_parm(example_id=new_example_id)
                    st.session_state["__example_docs"].append(doc_ref.get())
                    st.experimental_rerun()

            st.success("Saved", icon="✅")

    def state_to_doc(self, state: dict):
        return {
            field_name: deepcopy(state[field_name])
            for field_name in self.fields_to_save()
            if field_name in state
        } | {
            "updated_at": datetime.datetime.utcnow(),
        }

    def fields_to_save(self) -> [str]:
        # only save the fields in request/response
        return [
            field_name
            for model in (self.RequestModel, self.ResponseModel)
            for field_name in model.__fields__
        ]

    def _examples_tab(self):
        example_docs = st.session_state.setdefault("__example_docs", [])
        if not example_docs:
            with st.spinner("Loading Examples..."):
                example_docs.extend(
                    db.list_all_docs(
                        document_id=self.doc_name,
                        sub_collection_id=EXAMPLES_COLLECTION,
                    )
                )

        allow_delete = is_admin()

        for snapshot in example_docs:
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
                copy_to_clipboard_button("🔗 Copy URL", value=url)

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

    def preview_title(self, state: dict, run_id: str, uid: str, example_id: str) -> str:
        input_as_text = state.get("text_prompt", state.get("input_prompt"))
        prev_title = f"{self.title}"  # PREVIEW TITLE
        if run_id and uid:
            prev_title = self._build_preview_title_for_run(input_as_text, uid)
            return f"{prev_title} on Gooey.AI"
        if example_id and input_as_text:
            prev_title = f"{input_as_text[:100]} ... {self.title}"
            return f"{prev_title} on Gooey.AI"
        return f"{prev_title} • AI API, workflow & prompt shared on Gooey.AI"

    def _build_preview_title_for_run(self, input_as_text, uid):
        if input_as_text:
            # INPUT PROMPT
            title = f"{input_as_text[:100]} ... "

            # USER NAME
            user_ref = get_user_doc_ref(uid)
            user = user_ref.get().to_dict()
            if "name" in user:
                name = user.get("name")
                title += f"• {name}'s "

            # RECIPE TITLE
            title += f"{self.title}"
            return title
        return ""

    def render_steps(self):
        pass

    def preview_title(self, state: dict, query_params: dict) -> str:
        input_as_text = state.get("text_prompt", state.get("input_prompt"))
        example_id, run_id, uid = self.extract_query_params(query_params)
        title = f"{self.title}"
        if (run_id and uid) or example_id:
            if input_as_text:
                title = f"{input_as_text[:100]} ... {self.title}"
        return f"{title} • AI API, workflow & prompt shared on Gooey.AI"

    def preview_description(self, state: dict) -> str:
        pass

    def preview_image(self, state: dict) -> str:
        images = state.get(
            "output_images",
            state.get("output_image", state.get("cutout_image", "")),
        )
        if images:
            if isinstance(images, list):
                return images[0]
            elif isinstance(images, dict):
                first_value = next(iter(images.values()))
                if isinstance(first_value, list) and first_value:
                    return first_value[0]
                elif isinstance(first_value, str) and first_value:
                    return first_value
            else:
                return images
        return GOOEY_LOGO

    def run_as_api_tab(self):
        api_docs_url = str(
            furl(
                settings.API_BASE_URL,
                fragment_path=f"operation/{self.slug_versions[0]}",
            )
            / "docs"
        )
        st.markdown(f"### [📖 API Docs]({api_docs_url})")

        api_url = str(furl(settings.API_BASE_URL) / self.endpoint)
        request_body = get_example_request_body(self.RequestModel, st.session_state)
        response_body = self.get_example_response_body(st.session_state)

        st.write("#### 📤 Example Request")
        with st.columns([3, 1])[0]:
            api_example_generator(api_url, request_body)

        user = st.session_state.get("_current_user")
        if hasattr(user, "_is_anonymous"):
            st.write("**Please Login to generate the `$GOOEY_API_KEY`**")
            return

        st.write("#### 🎁 Example Response")
        st.json(response_body, expanded=False)

        st.write("---")
        st.write("### 🔐 API keys")

        with st.columns([3, 1])[0]:
            manage_api_keys(user)

    def check_credits(self) -> bool:
        user = st.session_state.get("_current_user")
        if not user:
            return True

        balance = db.get_doc_field(
            db.get_user_doc_ref(user.uid), db.USER_BALANCE_FIELD, 0
        )

        if balance < self.get_price():
            account_url = furl(settings.APP_BASE_URL) / "account"
            if getattr(user, "_is_anonymous", False):
                account_url.query.params["next"] = self._get_current_url()
                error = f"Doh! You need to login to run more Gooey.AI recipes. [Login]({account_url})"
            else:
                error = f"Doh! You need to purchase additional credits to run more Gooey.AI recipes. [Buy Credits]({account_url})"
            st.error(error, icon="⚠️")
            return False

        return True

    def deduct_credits(self):
        user = st.session_state.get("_current_user")
        if not user:
            return

        amount = self.get_price()
        db.update_user_balance(user.uid, -abs(amount), f"gooey_in_{uuid.uuid1()}")

    def get_price(self) -> int:
        return self.price

    def get_example_response_body(self, state: dict) -> dict:
        example_id, run_id, uid = self.extract_query_params(
            st.experimental_get_query_params()
        )
        return dict(
            id=run_id or example_id or get_random_doc_id(),
            url=self._get_current_url(),
            created_at=datetime.datetime.utcnow().isoformat(),
            output=get_example_request_body(self.ResponseModel, state),
        )


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
