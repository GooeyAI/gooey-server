import datetime
import inspect
import traceback
import typing
import uuid
from copy import deepcopy
from time import time, sleep

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
from streamlit_option_menu import option_menu

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
from daras_ai_v2.grid_layout_widget import grid_layout, SkipIteration
from daras_ai_v2.hidden_html_widget import hidden_html_js
from daras_ai_v2.html_error_widget import html_error
from daras_ai_v2.html_spinner_widget import html_spinner
from daras_ai_v2.manage_api_keys_widget import manage_api_keys
from daras_ai_v2.patch_widgets import ensure_hidden_widgets_loaded
from daras_ai_v2.meta_preview_url import meta_preview_url
from daras_ai_v2.query_params import gooey_reset_query_parm
from daras_ai_v2.settings import APP_BASE_URL
from daras_ai_v2.utils import email_support_about_reported_run
from daras_ai_v2.utils import random


DEFAULT_STATUS = "Running..."

EXAMPLES_COLLECTION = "examples"
USER_RUNS_COLLECTION = "user_runs"

EXAMPLE_ID_QUERY_PARAM = "example_id"
RUN_ID_QUERY_PARAM = "run_id"
USER_ID_QUERY_PARAM = "uid"
DEFAULT_META_IMG = (
    # "https://storage.googleapis.com/dara-c1b52.appspot.com/meta_tag_default_img.jpg"
    "https://storage.googleapis.com/dara-c1b52.appspot.com/meta_tag_gif.gif"
)

O = typing.TypeVar("O")


class ApiResponseModel(GenericModel, typing.Generic[O]):
    id: str
    url: str
    created_at: str
    output: O


class MenuTabs:
    run = "🏃‍♀️Run"
    examples = "🔖 Examples"
    run_as_api = "🚀 Run as API"
    history = "📖 History"


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
        query_params = cls._clean_query_params(example_id, run_id, uid)
        return str(
            furl(settings.APP_BASE_URL, query_params=query_params)
            / (cls.slug_versions[-1] + "/")
        )

    @classmethod
    def _clean_query_params(cls, example_id, run_id, uid) -> dict:
        query_params = {}
        if run_id and uid:
            query_params |= dict(run_id=run_id, uid=uid)
        if example_id:
            query_params |= dict(example_id=example_id)
        return query_params

    def api_url(self, example_id=None, run_id=None, uid=None) -> str:
        query_params = {}
        if run_id and uid:
            query_params = dict(run_id=run_id, uid=uid)
        elif example_id:
            query_params = dict(example_id=example_id)
        return str(
            furl(settings.API_BASE_URL, query_params=query_params) / self.endpoint
        )

    @property
    def endpoint(self) -> str:
        return f"/v2/{self.slug_versions[0]}/"

    def render(self):
        try:
            ensure_hidden_widgets_loaded(st.session_state.pop("__prev_state", {}))
            self._render()
        except Exception as e:
            sentry_sdk.capture_exception(e)
            raise
        finally:
            st.session_state["__prev_state"] = dict(st.session_state)

    def _render(self):
        with sentry_sdk.configure_scope() as scope:
            scope.set_extra("url", self.app_url())
            scope.set_extra("query_params", st.experimental_get_query_params())
            scope.set_transaction_name(
                "/" + self.slug_versions[0], source=TRANSACTION_SOURCE_ROUTE
            )

        init_scripts()

        self._load_session_state()
        self._check_if_flagged()

        if st.session_state.get("show_report_workflow"):
            self.render_report_form()
            return

        st.session_state.setdefault("__title", self.title)
        st.session_state.setdefault(
            "__notes", self.preview_description(st.session_state)
        )

        st.write("## " + st.session_state.get("__title"))
        st.write(st.session_state.get("__notes"))

        menu_options = [MenuTabs.run, MenuTabs.examples, MenuTabs.run_as_api]

        current_user: UserRecord = st.session_state.get("_current_user")
        if not hasattr(current_user, "_is_anonymous"):
            menu_options.append(MenuTabs.history)

        selected_menu = option_menu(
            None,
            options=menu_options,
            icons=["-"] * len(menu_options),
            orientation="horizontal",
            key=st.session_state.get("__option_menu_key"),
            styles={
                "nav-link": {"white-space": "nowrap;"},
                "nav-link-selected": {"font-weight": "normal;", "color": "black"},
            },
        )

        if selected_menu == MenuTabs.run:
            input_col, output_col = st.columns([3, 2], gap="medium")

            self._render_step_row()

            col1, col2 = st.columns(2)
            with col1:
                self._render_help()

            self.render_related_workflows()

            with input_col:
                submitted1 = self.render_form()

                with st.expander("⚙️ Settings"):
                    self.render_settings()

                    st.write("---")
                    st.write("##### 🖌️ Personalize")
                    st.text_input("Title", key="__title")
                    st.text_area("Notes", key="__notes")
                    st.write("---")

                    submitted2 = self.render_submit_button(key="--submit-2")

                submitted = submitted1 or submitted2

            with output_col:
                self._runner(submitted)

            with col2:
                self._render_save_options()
            #
            # NOTE: Beware of putting code here since runner will call experimental_rerun
            #

        elif selected_menu == MenuTabs.examples:
            self._examples_tab()

        elif selected_menu == MenuTabs.history:
            self._history_tab()

        elif selected_menu == MenuTabs.run_as_api:
            self.run_as_api_tab()

    def render_related_workflows(self):
        st.markdown(
            f"""
            <a style="text-decoration:none" href="{APP_BASE_URL}explore" target = "_top">
                <h2>Related Workflows</h2>
            </a>
            """,
            unsafe_allow_html=True,
        )
        workflows = self.related_workflows()
        cols = st.columns(len(workflows))
        for workflow in workflows:
            state = workflow().get_recipe_doc().to_dict()
            cols[workflows.index(workflow)].markdown(
                f"""
        <a href="{workflow().app_url()}" style="text-decoration:none;color:white">
        <img width=300px src="{meta_preview_url(workflow().preview_image(state))}" />
        <h4>{workflow().title}</h4>
        {workflow().preview_description(state)}
        </a>
        """,
                unsafe_allow_html=True,
            )

    def related_workflows(self) -> list:
        pass

    def render_report_form(self):
        with st.form("report_form"):
            st.write(
                """
                ## Report a Workflow
                Generative AI is powerful, but these technologies are also unmoderated. Sometimes the output of workflows can be inappropriate or incorrect. It might be broken or buggy. It might cause copyright issues. It might be inappropriate content.
                Whatever the reason, please use this form to tell us when something is wrong with the output of a workflow you've run or seen on our site.
                We'll investigate the reported workflow and its output and take appropriate action. We may flag this workflow or its author so they are aware too.
                """
            )

            st.write("#### Your Report")

            st.text_input(
                "Workflow",
                disabled=True,
                value=self.title,
            )

            current_url = self._get_current_app_url()
            st.text_input(
                "Run URL",
                disabled=True,
                value=current_url,
            )

            st.write("Output")
            self.render_output()

            inappropriate_radio_text = "Inappropriate content"
            report_type = st.radio(
                "Report Type", ("Buggy Output", inappropriate_radio_text, "Other")
            )
            reason_for_report = st.text_area(
                "Reason for report",
                placeholder="Tell us why you are reporting this workflow e.g. an error, inappropriate content, very poor output, etc. Please let know what you expected as well. ",
            )

            col1, col2 = st.columns(2)
            with col1:
                submitted = st.form_submit_button("Submit Report")
            with col2:
                cancelled = st.form_submit_button("Cancel")

        if cancelled:
            st.session_state["show_report_workflow"] = False
            st.experimental_rerun()

        if submitted:
            if reason_for_report == "":
                st.error("Reason for report cannot be empty")
                return

            with st.spinner("Reporting..."):
                current_user: UserRecord = st.session_state.get("_current_user")

                query_params = st.experimental_get_query_params()
                example_id, run_id, uid = self.extract_query_params(query_params)

                email_support_about_reported_run(
                    uid=uid,
                    url=self._get_current_app_url(),
                    email=current_user.email,
                    recipe_name=self.title,
                    report_type=report_type,
                    reason_for_report=reason_for_report,
                )

                if report_type == inappropriate_radio_text:
                    self.update_flag_for_run(run_id=run_id, uid=uid, is_flagged=True)

            st.success("Reported.", icon="✅")
            sleep(2)
            st.session_state["show_report_workflow"] = False
            st.experimental_rerun()

    def _load_session_state(self):
        placeholder = st.empty()

        if st.session_state.get("__loaded__"):
            return

        with placeholder.container(), st.spinner("Loading Settings..."):
            query_params = st.experimental_get_query_params()
            doc = self.get_doc_from_query_params(query_params)

            if doc is None:
                st.write("### 404: We can't find this page!")
                st.stop()

            self._update_session_state(doc)

    def _update_session_state(self, doc):
        st.session_state.update(doc)
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
            st.success("Removed flag.", icon="✅")
            sleep(2)
            st.experimental_rerun()
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
        if run_id and uid:
            snapshot = self.run_doc_ref(run_id, uid).get()
        elif example_id:
            snapshot = self._example_doc_ref(example_id).get()
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
        self.render_form_v2()
        return self.render_submit_button()

    def get_credits_click_url(self):
        current_user: UserRecord = st.session_state.get("_current_user")
        if hasattr(current_user, "_is_anonymous"):
            return "/pricing/"
        else:
            return "/account/"

    def render_submit_button(self, key="--submit-1"):
        col1, col2 = st.columns([2, 1])
        with col1:
            st.caption(
                f"_By submitting, you agree to Gooey.AI's [terms](https://gooey.ai/terms) & [privacy policy](https://gooey.ai/privacy)._ \\\n"
                f"Run cost: [{self.get_price()} credits]({self.get_credits_click_url()})",
            )
        with col2:
            submitted = st.button("🏃 Submit", key=key, type="primary")
        if not submitted:
            return False
        try:
            self.validate_form_v2()
        except AssertionError as e:
            st.error(e, icon="⚠️")
            return False
        else:
            return True

    def _render_step_row(self):
        with st.expander("**ℹ️ Details**"):
            col1, col2 = st.columns([1, 2])
            with col1:
                self.render_description()
            with col2:
                placeholder = st.empty()
                try:
                    self.render_steps()
                except NotImplementedError:
                    pass
                else:
                    with placeholder:
                        st.write("##### 👣 Steps")

    def _render_help(self):
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
            f"**🙋🏽‍♀️ Need more help? [Join our Discord]({settings.DISCORD_INVITE_URL})**",
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

        st.session_state["show_report_workflow"] = reported
        st.experimental_rerun()

    def _render_before_output(self):
        query_params = st.experimental_get_query_params()
        example_id, run_id, uid = self.extract_query_params(query_params)
        if not (run_id or example_id):
            return

        url = self._get_current_app_url()
        if not url:
            return

        col1, col2 = st.columns([2, 1])

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

    def _get_current_app_url(self) -> str | None:
        query_params = st.experimental_get_query_params()
        example_id, run_id, uid = self.extract_query_params(query_params)
        return self.app_url(example_id, run_id, uid)

    def _get_current_api_url(self) -> str | None:
        query_params = st.experimental_get_query_params()
        example_id, run_id, uid = self.extract_query_params(query_params)
        return self.api_url(example_id, run_id, uid)

    def update_flag_for_run(self, run_id: str, uid: str, is_flagged: bool):
        ref = self.run_doc_ref(uid=uid, run_id=run_id)
        updates = {"is_flagged": is_flagged}
        ref.update(updates)
        st.session_state.update(updates)

    def save_run(self, new_run: bool = False):
        current_user: auth.UserRecord = st.session_state.get("_current_user")
        if not current_user:
            return

        query_params = st.experimental_get_query_params()
        example_id, run_id, _ = self.extract_query_params(query_params)
        if new_run:
            run_id = get_random_doc_id()
        gooey_reset_query_parm(
            **self._clean_query_params(
                example_id=example_id, run_id=run_id, uid=current_user.uid
            )
        )

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
            with status_area:
                html_spinner("Starting...")

            self._pre_run_checklist()
            if not self.check_credits():
                status_area.empty()
                return

            st.session_state["__status"] = DEFAULT_STATUS
            st.session_state["__time_taken"] = 0
            st.session_state["__gen"] = self.run(st.session_state)

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
                st.session_state["__time_taken"] = (
                    st.session_state.get("__time_taken", 0) + time() - start_time
                )

            except StopIteration:
                # Weird but important! This measures the runtime of code after the last `yield` in `run()`
                if start_time:
                    st.session_state["__time_taken"] = (
                        st.session_state.get("__time_taken", 0) + time() - start_time
                    )

                # save a snapshot of the params used to create this output
                st.session_state["__state_to_save"] = self.state_to_doc(
                    st.session_state
                )

                # cleanup is important!
                st.session_state.pop("__status", None)
                st.session_state.pop("__gen", None)

                self.deduct_credits()

            # render errors nicely
            except Exception as e:
                sentry_sdk.capture_exception(e)
                traceback.print_exc()
                with status_area:
                    st.error(err_msg_for_exc(e), icon="⚠️")
                # cleanup is important!
                st.session_state.pop("__status", None)
                st.session_state.pop("__gen", None)
                st.session_state.pop("__time_taken", None)
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
        self.save_run(new_run=True)

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

    def _render_save_options(self):
        state_to_save = st.session_state.get("__state_to_save")
        # st.write("state_to_save " + str(state_to_save))
        if not state_to_save:
            return

        if not is_admin():
            return

        new_example_id = None
        doc_ref = None
        query_params = st.experimental_get_query_params()

        with st.expander("🛠️ Admin Options"):
            col1, col2, col3 = st.columns(3)

            with col1:
                if st.button("⭐️ Save Workflow & Settings"):
                    doc_ref = db.get_doc_ref(self.doc_name)

            with col2:
                if st.button("🔖 Add as Example"):
                    new_example_id = get_random_doc_id()
                    doc_ref = self._example_doc_ref(new_example_id)
                    gooey_reset_query_parm(example_id=new_example_id)

            with col3:
                if EXAMPLE_ID_QUERY_PARAM in query_params and st.button(
                    "💾 Save Example & Settings"
                ):
                    example_id = query_params[EXAMPLE_ID_QUERY_PARAM][0]
                    doc_ref = self._example_doc_ref(example_id)
                    gooey_reset_query_parm(example_id=example_id)

            if not doc_ref:
                return

            with st.spinner("Saving..."):
                doc_ref.set(state_to_save)

                if new_example_id:
                    st.session_state.get("__example_docs", []).insert(0, doc_ref.get())
                    st.experimental_rerun()

            st.success("Saved", icon="✅")

    def state_to_doc(self, state: dict):
        ret = {
            field_name: deepcopy(state[field_name])
            for field_name in self.fields_to_save()
            if field_name in state
        }
        ret |= {
            "updated_at": datetime.datetime.utcnow(),
        }

        title = state.get("__title")
        notes = state.get("__notes")
        if title and title.strip() != self.title.strip():
            ret["__title"] = title
        if notes and notes.strip() != self.preview_description(state).strip():
            ret["__notes"] = notes

        return ret

    def fields_to_save(self) -> [str]:
        # only save the fields in request/response
        return [
            field_name
            for model in (self.RequestModel, self.ResponseModel)
            for field_name in model.__fields__
        ]

    def _examples_tab(self):
        if "__example_docs" not in st.session_state:
            with st.spinner("Loading Examples..."):
                example_docs = db.get_collection_ref(
                    document_id=self.doc_name,
                    sub_collection_id=EXAMPLES_COLLECTION,
                ).get()
                example_docs.sort(
                    key=lambda s: s.to_dict()
                    .get("updated_at", datetime.datetime.fromtimestamp(0))
                    .timestamp(),
                    reverse=True,
                )
            st.session_state["__example_docs"] = example_docs
        example_docs = st.session_state.get("__example_docs")

        allow_delete = is_admin()

        def _render(snapshot):
            example_id = snapshot.id
            doc = snapshot.to_dict()

            if doc.get("__hidden"):
                raise SkipIteration()

            url = str(
                furl(
                    self.app_url(),
                    query_params={EXAMPLE_ID_QUERY_PARAM: example_id},
                )
            )
            self._render_doc_example(
                allow_delete=allow_delete,
                doc=doc,
                url=url,
                query_params=dict(example_id=example_id),
            )

        grid_layout(2, example_docs, _render)

    def _history_tab(self):
        current_user = st.session_state.get("_current_user")
        uid = current_user.uid
        run_history = st.session_state.get("__run_history", [])

        def _render(snapshot):
            run_id = snapshot.id
            doc = snapshot.to_dict()

            url = str(
                furl(
                    self.app_url(),
                    query_params={
                        RUN_ID_QUERY_PARAM: run_id,
                        USER_ID_QUERY_PARAM: uid,
                    },
                )
            )

            self._render_doc_example(
                allow_delete=False,
                doc=doc,
                url=url,
                query_params=dict(run_id=run_id, uid=uid),
            )

        grid_layout(2, run_history, _render)

        if "__run_history" not in st.session_state or st.button("Load More"):
            with st.spinner("Loading History..."):
                run_history.extend(
                    db.get_collection_ref(
                        collection_id=USER_RUNS_COLLECTION,
                        document_id=uid,
                        sub_collection_id=self.doc_name,
                    )
                    .order_by("updated_at", direction="DESCENDING")
                    .offset(len(run_history))
                    .limit(20)
                    .get()
                )
            st.session_state["__run_history"] = run_history
            st.experimental_rerun()

    def _render_doc_example(
        self, *, allow_delete: bool, doc: dict, url: str, query_params: dict
    ):
        col1, col2 = st.columns([2, 6])

        with col1:
            if st.button("✏️ Tweak", help=f"Tweak {query_params}"):
                # change url
                gooey_reset_query_parm(**query_params)

                # scroll to top
                hidden_html_js(
                    """
                    <script>
                      top.document.body.scrollTop = 0; // For Safari
                      top.document.documentElement.scrollTop = 0; // For Chrome, Firefox, IE and Opera
                    </script>
                    """
                )

                # update state
                st.session_state.clear()
                self._update_session_state(doc)

                # jump to run tab
                st.session_state["__option_menu_key"] = get_random_doc_id()

                # rerun
                sleep(0.01)
                st.experimental_rerun()

            copy_to_clipboard_button("🔗 Copy URL", value=url)

            if allow_delete:
                self._example_delete_button(**query_params)

        with col2:
            title = doc.get("__title")
            if title and title.strip() != self.title.strip():
                st.write("#### " + title)

            notes = doc.get("__notes")
            if (
                notes
                and notes.strip() != self.preview_description(st.session_state).strip()
            ):
                st.write(notes)

            self.render_example(doc)

    def _example_delete_button(self, example_id):
        pressed_delete = st.button(
            "🗑️ Delete",
            help=f"Delete example {example_id}",
        )
        if not pressed_delete:
            return

        example = self._example_doc_ref(example_id)

        with st.spinner("deleting..."):
            example.update({"__hidden": True})

        example_docs = st.session_state.get("__example_docs", [])
        for idx, snapshot in enumerate(example_docs):
            if snapshot.id == example_id:
                example_docs.pop(idx)
                st.experimental_rerun()

    def render_example(self, state: dict):
        pass

    def render_steps(self):
        raise NotImplementedError

    def preview_input(self, state: dict) -> str | None:
        return (
            state.get("text_prompt")
            or state.get("input_prompt")
            or state.get("search_query")
        )

    def preview_description(self, state: dict) -> str:
        return ""

    def preview_image(self, state: dict) -> str | None:
        out = (
            state.get("cutout_image")
            or state.get("output_images")
            or state.get("output_image")
            or state.get("output_video")
        )
        return extract_nested_str(out) or DEFAULT_META_IMG

    def run_as_api_tab(self):
        api_docs_url = str(
            furl(
                settings.API_BASE_URL,
                fragment_path=f"operation/{self.slug_versions[0]}",
            )
            / "docs"
        )
        st.markdown(f"### [📖 API Docs]({api_docs_url})")

        api_url = self._get_current_api_url()
        request_body = get_example_request_body(self.RequestModel, st.session_state)
        response_body = self.get_example_response_body(st.session_state)

        st.write("#### 📤 Example Request")
        api_example_generator(api_url, request_body)

        user = st.session_state.get("_current_user")
        if hasattr(user, "_is_anonymous"):
            st.write("**Please Login to generate the `$GOOEY_API_KEY`**")
            return

        st.write("#### 🎁 Example Response")
        st.json(response_body, expanded=False)

        st.write("---")
        st.write("### 🔐 API keys")

        manage_api_keys(user)

    def check_credits(self) -> bool:
        user = st.session_state.get("_current_user")
        if not user:
            return True

        balance = db.get_doc_field(
            db.get_user_doc_ref(user.uid), db.USER_BALANCE_FIELD, 0
        )

        if balance < self.get_price():
            account_url = furl(settings.APP_BASE_URL) / "account/"

            if getattr(user, "_is_anonymous", False):
                account_url.query.params["next"] = self._get_current_app_url()
                error = f"""
                <p>
                Doh! <a href="{account_url}" target="_top">Please login</a> to run more Gooey.AI workflows.
                </p>
                                
                You’ll receive {settings.LOGIN_USER_FREE_CREDITS} Gooey.AI credits (for ~200 Runs). 
                You can <a href="/pricing/" target="_blank">purchase more</a> if you run out of credits.
                """
            else:
                error = f"""
                <p>
                Doh! You’re out of Gooey.AI credits.
                </p>
                                
                <p>
                Please <a href="{settings.GRANT_URL}" target="_blank">apply for a grant</a> or 
                <a href="{account_url}" target="_blank">buy more</a> to run more workflows.
                </p>
                                
                We’re always on <a href="{settings.DISCORD_INVITE_URL}" target="_blank">discord</a> if you’ve got any questions.
                """

            html_error(error)
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
            url=self._get_current_app_url(),
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


def extract_nested_str(obj) -> str:
    if isinstance(obj, str):
        return obj
    elif isinstance(obj, dict):
        obj = obj.values()
    try:
        items = iter(obj)
    except TypeError:
        pass
    else:
        for it in items:
            if it:
                return extract_nested_str(it)
    return ""


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
