import datetime
import inspect
import math
import traceback
import typing
import uuid
from copy import deepcopy
from random import Random
from threading import Thread
from time import time, sleep

import requests
import sentry_sdk
from firebase_admin import auth
from firebase_admin.auth import UserRecord
from furl import furl
from google.cloud import firestore
from pydantic import BaseModel
from sentry_sdk.tracing import (
    TRANSACTION_SOURCE_ROUTE,
)

import gooey_ui as st
from daras_ai_v2 import db
from daras_ai_v2 import settings
from daras_ai_v2.api_examples_widget import api_example_generator
from daras_ai_v2.copy_to_clipboard_button_widget import (
    copy_to_clipboard_button,
)
from daras_ai_v2.crypto import (
    get_random_doc_id,
)
from daras_ai_v2.db import USER_RUNS_COLLECTION, EXAMPLES_COLLECTION
from daras_ai_v2.grid_layout_widget import grid_layout, SkipIteration
from daras_ai_v2.html_error_widget import html_error
from daras_ai_v2.html_spinner_widget import html_spinner
from daras_ai_v2.html_spinner_widget import (
    scroll_to_top,
)
from daras_ai_v2.manage_api_keys_widget import manage_api_keys
from daras_ai_v2.meta_preview_url import meta_preview_url
from daras_ai_v2.perf_timer import perf_timer, start_perf_timer

# from daras_ai_v2.patch_widgets import ensure_hidden_widgets_loaded
from daras_ai_v2.query_params import (
    gooey_reset_query_parm,
    gooey_get_query_params,
    QUERY_PARAMS_KEY,
)
from daras_ai_v2.query_params_util import (
    extract_query_params,
    EXAMPLE_ID_QUERY_PARAM,
    RUN_ID_QUERY_PARAM,
    USER_ID_QUERY_PARAM,
)
from daras_ai_v2.send_email import send_reported_run_email
from daras_ai_v2.settings import EXPLORE_URL
from daras_ai_v2.tabs_widget import MenuTabs
from daras_ai_v2.user_date_widgets import render_js_dynamic_dates, js_dynamic_date
from routers.realtime import realtime_subscribe, realtime_set

DEFAULT_META_IMG = (
    # Small
    "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/optimized%20hp%20gif.gif"
    # "https://storage.googleapis.com/dara-c1b52.appspot.com/meta_tag_default_img.jpg"
    # Big
    # "https://storage.googleapis.com/dara-c1b52.appspot.com/meta_tag_gif.gif"
)
MAX_SEED = 4294967294
gooey_rng = Random()


class StateKeys:
    page_title = "__title"
    page_notes = "__notes"

    option_menu_key = "__option_menu_key"

    updated_at = "updated_at"

    error_msg = "__error_msg"
    run_time = "__run_time"
    run_status = "__run_status"
    pressed_randomize = "__randomize"

    examples_cache = "__examples_cache"
    history_cache = "__history_cache"

    query_params = QUERY_PARAMS_KEY


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
    def app_url(cls, example_id=None, run_id=None, uid=None, tab_path=None) -> str:
        query_params = cls.clean_query_params(example_id, run_id, uid)
        f = furl(settings.APP_BASE_URL, query_params=query_params) / (
            cls.slug_versions[-1] + "/"
        )
        if tab_path:
            f /= tab_path
        return str(f)

    @classmethod
    def clean_query_params(cls, example_id, run_id, uid) -> dict:
        query_params = {}
        if run_id and uid:
            query_params |= dict(run_id=run_id, uid=uid)
        if example_id:
            query_params |= dict(example_id=example_id)
        return query_params

    def api_url(self, example_id=None, run_id=None, uid=None) -> furl:
        query_params = {}
        if run_id and uid:
            query_params = dict(run_id=run_id, uid=uid)
        elif example_id:
            query_params = dict(example_id=example_id)
        return furl(settings.API_BASE_URL, query_params=query_params) / self.endpoint

    @property
    def endpoint(self) -> str:
        return f"/v2/{self.slug_versions[0]}/"

    def render(self):
        try:
            self._render()
        except Exception as e:
            sentry_sdk.capture_exception(e)
            raise
        finally:
            pass
            # ensure_hidden_widgets_loaded()

    def _render(self):
        with sentry_sdk.configure_scope() as scope:
            scope.set_extra("base_url", self.app_url())
            scope.set_transaction_name(
                "/" + self.slug_versions[0], source=TRANSACTION_SOURCE_ROUTE
            )

        self._user_disabled_check()

        # self._realtime_subscribe()
        self._load_session_state()
        self._check_if_flagged()

        if st.session_state.get("show_report_workflow"):
            self.render_report_form()
            return

        st.session_state.setdefault(StateKeys.page_title, self.title)
        st.session_state.setdefault(
            StateKeys.page_notes, self.preview_description(st.session_state)
        )

        example_id, run_id, uid = extract_query_params(gooey_get_query_params())
        root_url = self.app_url(example_id=example_id)
        st.write(
            f'## <a style="text-decoration: none;" target="_top" href="{root_url}">{st.session_state.get(StateKeys.page_title)}</a>',
            unsafe_allow_html=True,
        )
        st.write(st.session_state.get(StateKeys.page_notes))

        selected_tab_path = st.get_query_params().get("tab", "")
        try:
            selected_tab = MenuTabs.paths_reverse[selected_tab_path]
        except KeyError:
            st.error(f"## 404 - Tab {selected_tab_path!r} Not found")
            return

        tab_names = self.get_tabs()
        st.write("---")
        for name in tab_names:
            bgcolor = "gray" if name == selected_tab else "transparent"
            url = self.app_url(
                *extract_query_params(gooey_get_query_params()),
                tab_path=MenuTabs.paths[name],
            )
            st.markdown(
                # language=html
                f"""
<a href="{url}" 
    style="font-size: 1.25rem; background-color: {bgcolor}">
{name}
</a>""",
            )
        st.write("---")

        self.render_selected_tab(selected_tab)
        render_js_dynamic_dates()

    def _user_disabled_check(self):
        run_user: UserRecord = st.session_state.get("_run_user")
        if run_user and run_user.disabled:
            msg = (
                "This Gooey.AI account has been disabled for violating our [Terms of Service](/terms). "
                "Contact us at support@gooey.ai if you think this is a mistake."
            )
            st.error(msg, icon="😵")
            st.stop()

    def _realtime_subscribe(self):
        _, run_id, uid = extract_query_params(gooey_get_query_params())
        redis_key = f"runs/{uid}/{run_id}"
        updates = realtime_subscribe(redis_key)
        if updates:
            st.session_state.update(updates)
        else:
            st.session_state[StateKeys.run_status] = None

    def get_tabs(self):
        tabs = [MenuTabs.run, MenuTabs.examples, MenuTabs.run_as_api]
        current_user: UserRecord = st.session_state.get("_current_user")
        if not hasattr(current_user, "_is_anonymous"):
            tabs.extend([MenuTabs.history])
        return tabs

    def render_selected_tab(self, selected_tab: str):
        match selected_tab:
            case MenuTabs.run:
                input_col, output_col = st.columns([3, 2], gap="medium")
                with input_col:
                    self.render_author()
                    submitted1 = self.render_form()
                    with st.expander("⚙️ Settings"):
                        self.render_settings()
                        st.write("---")
                        st.write("##### 🖌️ Personalize")
                        st.text_input("Title", key=StateKeys.page_title)
                        st.text_area("Notes", key=StateKeys.page_notes)
                        st.write("---")
                        submitted2 = self.render_submit_button(key="--submit-2")
                    submitted = submitted1 or submitted2
                with output_col:
                    self._render_output_col(submitted)

                self._render_step_row()

                col1, col2 = st.columns(2)
                with col1:
                    self._render_help()
                with col2:
                    self._render_save_options()

                self.render_related_workflows()

            case MenuTabs.examples:
                self._examples_tab()

            case MenuTabs.history:
                self._history_tab()

            case MenuTabs.run_as_api:
                self.run_as_api_tab()

    def render_related_workflows(self):
        workflows = self.related_workflows()
        if not workflows:
            return
        st.markdown(
            f"""
            <a style="text-decoration:none" href="{EXPLORE_URL}" target = "_top">
                <h2>Related Workflows</h2>
            </a>
            """,
            unsafe_allow_html=True,
        )

        def _build_page_tuple(page: typing.Type[BasePage]):
            state = page().get_recipe_doc().to_dict()
            preview_image = meta_preview_url(
                page().preview_image(state), page().fallback_preivew_image()
            )
            return page, state, preview_image

        # if "__related_recipe_docs" not in st.session_state:
        #     with st.spinner("Loading Related Recipes..."):
        #         docs = map_parallel(
        #             _build_page_tuple,
        #             workflows,
        #         )
        #     st.session_state["__related_recipe_docs"] = docs
        # related_recipe_docs = st.session_state.get("__related_recipe_docs")
        related_recipe_docs = []

        def _render(page_tuple):
            page, state, preview_image = page_tuple
            st.markdown(
                f"""
                <a href="{page().app_url()}" style="text-decoration:none;color:white">
                    <p>
                            <div style="width:100%;height:150px;background-image: url({preview_image}); background-size:cover; background-position-x:center; background-position-y:30%; background-repeat:no-repeat;"></div>
                            <h5>{page().title}</h5>
                            <p style="color:grey;font-size:16px">{page().preview_description(state)}</p>
                    </p>
                </a>
                <br/>
                """,
                unsafe_allow_html=True,
            )

        grid_layout(4, related_recipe_docs, _render)

    def related_workflows(self) -> list:
        return []

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
                submitted = st.form_submit_button("✅ Submit Report")
            with col2:
                cancelled = st.form_submit_button("❌ Cancel")

        if cancelled:
            st.session_state["show_report_workflow"] = False
            st.experimental_rerun()

        if submitted:
            if reason_for_report == "":
                st.error("Reason for report cannot be empty")
                return

            with st.spinner("Reporting..."):
                current_user: UserRecord = st.session_state.get("_current_user")

                example_id, run_id, uid = extract_query_params(gooey_get_query_params())

                send_reported_run_email(
                    user=current_user,
                    run_uid=uid,
                    url=self._get_current_app_url(),
                    recipe_name=self.title,
                    report_type=report_type,
                    reason_for_report=reason_for_report,
                    error_msg=st.session_state.get(StateKeys.error_msg),
                )

                if report_type == inappropriate_radio_text:
                    self.update_flag_for_run(run_id=run_id, uid=uid, is_flagged=True)

            st.success("Reported.", icon="✅")
            sleep(2)
            st.session_state["show_report_workflow"] = False
            st.experimental_rerun()

    def _load_session_state(self):
        placeholder = st.div()

        if st.session_state.get("__loaded__"):
            return

        with placeholder, st.spinner("Loading Settings..."):
            doc = self.get_doc_from_query_params(gooey_get_query_params())

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
                example_id, run_id, uid = extract_query_params(gooey_get_query_params())
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

    def get_doc_from_query_params(self, query_params) -> dict | None:
        example_id, run_id, uid = extract_query_params(query_params)
        return self.get_firestore_state(example_id, run_id, uid)

    def get_firestore_state(self, example_id, run_id, uid):
        if run_id and uid:
            snapshot = self.run_doc_ref(run_id, uid).get()
        elif example_id:
            snapshot = self.example_doc_ref(example_id).get()
        else:
            snapshot = self.get_recipe_doc()
        return snapshot.to_dict()

    def get_recipe_doc(self) -> firestore.DocumentSnapshot:
        return db.get_or_create_doc(self.recipe_doc_ref())

    def recipe_doc_ref(self) -> firestore.DocumentReference:
        return db.get_doc_ref(self.doc_name)

    def run_doc_ref(self, run_id: str, uid: str) -> firestore.DocumentReference:
        return db.get_doc_ref(
            collection_id=USER_RUNS_COLLECTION,
            document_id=uid,
            sub_collection_id=self.doc_name,
            sub_document_id=run_id,
        )

    def example_doc_ref(self, example_id: str) -> firestore.DocumentReference:
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

    def _render_author(self, user):
        html = "<div style='display:flex; align-items:center; padding-bottom:16px'>"
        if user.photo_url:
            html += f"""
                <img style="width:38px; height:38px;border-radius:50%; pointer-events: none;" src="{user.photo_url}">
                <div style="width:8px;"></div>
            """
        if user.display_name:
            html += f"<div>{user.display_name}</div>"
        html += "</div>"
        st.markdown(
            html,
            unsafe_allow_html=True,
        )

    def render_author(self):
        if "_run_user" not in st.session_state:
            return
        user = st.session_state.get("_run_user")
        if not user.photo_url and not user.display_name:
            return
        self._render_author(user)

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
                f"Run cost = [{self.get_price_roundoff(st.session_state)} credits]({self.get_credits_click_url()})",
            )
            additional_notes = self.additional_notes()
            if additional_notes:
                st.caption(additional_notes)
        with col2:
            submitted = st.button(
                "🏃 Submit",
                key=key,
                type="primary",
                # disabled=bool(st.session_state.get(StateKeys.run_status)),
            )
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
                placeholder = st.div()
                try:
                    self.render_steps()
                except NotImplementedError:
                    pass
                else:
                    with placeholder:
                        st.write("##### 👣 Steps")

    def _render_help(self):
        placeholder = st.div()
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

        example_id, run_id, uid = extract_query_params(gooey_get_query_params())

        if not (current_user and run_id and uid):
            # ONLY RUNS CAN BE REPORTED
            return

        reported = st.button("❗Report")
        if not reported:
            return

        st.session_state["show_report_workflow"] = reported
        st.experimental_rerun()

    def _render_before_output(self):
        example_id, run_id, uid = extract_query_params(gooey_get_query_params())
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
        example_id, run_id, uid = extract_query_params(gooey_get_query_params())
        return self.app_url(example_id, run_id, uid)

    def _get_current_api_url(self) -> furl | None:
        example_id, run_id, uid = extract_query_params(gooey_get_query_params())
        return self.api_url(example_id, run_id, uid)

    def update_flag_for_run(self, run_id: str, uid: str, is_flagged: bool):
        ref = self.run_doc_ref(uid=uid, run_id=run_id)
        updates = {"is_flagged": is_flagged}
        ref.update(updates)
        st.session_state.update(updates)

    def create_new_run(self):
        current_user: auth.UserRecord = st.session_state["_current_user"]

        run_id = get_random_doc_id()
        example_id, *_ = extract_query_params(gooey_get_query_params())
        uid = current_user.uid

        Thread(
            target=self.run_doc_ref(run_id, uid).set,
            args=[self.state_to_doc(st.session_state)],
        ).start()
        gooey_reset_query_parm(
            **self.clean_query_params(example_id=example_id, run_id=run_id, uid=uid)
        )

        return run_id, uid

    def _render_output_col(self, submitted: bool):
        assert inspect.isgeneratorfunction(self.run)

        if st.session_state.get(StateKeys.pressed_randomize):
            st.session_state["seed"] = int(gooey_rng.randrange(MAX_SEED))
            st.session_state.pop(StateKeys.pressed_randomize, None)
            submitted = True

        if submitted:
            placeholder = st.div()
            with placeholder:
                html_spinner("Starting...")
            run_id, uid = self._pre_run_checklist()
            # scroll_to_spinner()
            if settings.CREDITS_TO_DEDUCT_PER_RUN and not self.check_credits():
                placeholder.empty()
                return
            self._run_in_thread(run_id, uid)
            sleep(0.1)
            st.experimental_rerun()

        run_status = st.session_state.get(StateKeys.run_status)
        if run_status:
            html_spinner(run_status)
        else:
            self._render_before_output()

            err_msg = st.session_state.get(StateKeys.error_msg)
            run_time = st.session_state.get(StateKeys.run_time, 0)

            # render errors
            if err_msg is not None:
                st.error(err_msg, icon="⚠️")
            # render run time
            elif run_time:
                st.success(
                    f"Success! Run Time: `{run_time:.2f}` seconds. ",
                    icon="✅",
                )

        # render outputs
        self.render_output()

        if run_status:
            pass
        else:
            self._render_after_output()

    def _run_in_thread(self, run_id, uid):
        if st.session_state.get(StateKeys.run_status):
            st.error("Already running, please wait or open in a new tab...")
            return

        t = Thread(
            target=self._run_thread,
            args=[run_id, uid, dict(st.session_state)],
        )
        t.start()

    def _run_thread(self, run_id, uid, local_state):
        redis_key = f"runs/{uid}/{run_id}"
        run_time = 0
        yield_val = None
        error_msg = None

        def save(done=False):
            updates = {
                StateKeys.run_time: run_time,
                StateKeys.error_msg: error_msg,
            }
            if done:
                # clear run status
                updates[StateKeys.run_status] = None
            else:
                # set run status to the yield value of generator
                updates[StateKeys.run_status] = yield_val or "Running..."
            # extract outputs from local state
            output = {
                k: v
                for k, v in local_state.items()
                if k in self.ResponseModel.__fields__
            }
            # send updates to streamlit
            realtime_set(
                redis_key, updates | output, expire=datetime.timedelta(hours=2)
            )
            # save to db
            self.run_doc_ref(run_id, uid).set(self.state_to_doc(updates | local_state))

        try:
            save()
            gen = self.run(local_state)
            while True:
                # record time
                start_time = time()
                try:
                    # advance the generator (to further progress of run())
                    yield_val = next(gen)
                    # increment total time taken after every iteration
                    run_time += time() - start_time
                    continue
                # run completed
                except StopIteration:
                    run_time += time() - start_time
                    self.deduct_credits(local_state)
                    break
                # render errors nicely
                except Exception as e:
                    run_time += time() - start_time
                    traceback.print_exc()
                    sentry_sdk.capture_exception(e)
                    error_msg = err_msg_for_exc(e)
                    break
                finally:
                    save()
        finally:
            save(done=True)

    def _pre_run_checklist(self):
        st.session_state.pop(StateKeys.run_status, None)
        st.session_state.pop(StateKeys.error_msg, None)
        st.session_state.pop(StateKeys.run_time, None)
        # st.session_state.pop(StateKeys.run_doc_to_save, None)
        self._setup_rng_seed()
        self.clear_outputs()
        return self.create_new_run()

    def _setup_rng_seed(self):
        seed = st.session_state.get("seed")
        if not seed:
            return
        gooey_rng.seed(seed)

    def clear_outputs(self):
        # clear error msg
        st.session_state.pop(StateKeys.error_msg, None)
        # clear outputs
        for field_name in self.ResponseModel.__fields__:
            st.session_state.pop(field_name, None)

    def _render_after_output(self):
        if "seed" in self.RequestModel.schema_json():
            seed = st.session_state.get("seed")
            # st.write("is_admin" + str(is_admin()))
            col1, col2, col3 = st.columns([1.5, 2, 1.5])
            with col1:
                st.caption(f"*Seed\\\n`{seed}`*")
            with col2:
                randomize = st.button("♻️ Regenerate")
                if randomize:
                    st.session_state[StateKeys.pressed_randomize] = True
                    st.experimental_rerun()
            with col3:
                self._render_report_button()
        else:
            self._render_report_button()

    def _render_save_options(self):
        if not is_admin():
            return

        new_example_id = None
        doc_ref = None
        example_id, *_ = extract_query_params(gooey_get_query_params())

        with st.expander("🛠️ Admin Options"):
            col1, col2, col3 = st.columns(3)

            with col1:
                if st.button("⭐️ Save Workflow & Settings"):
                    doc_ref = db.get_doc_ref(self.doc_name)

            with col2:
                if st.button("🔖 Add as Example"):
                    new_example_id = get_random_doc_id()
                    doc_ref = self.example_doc_ref(new_example_id)
                    gooey_reset_query_parm(example_id=new_example_id)

            with col3:
                if example_id and st.button("💾 Save Example & Settings"):
                    doc_ref = self.example_doc_ref(example_id)
                    gooey_reset_query_parm(example_id=example_id)

            if not doc_ref:
                return

            with st.spinner("Saving..."):
                doc_ref.set(self.state_to_doc(st.session_state))

                if new_example_id:
                    st.session_state.get(StateKeys.examples_cache, []).insert(
                        0, doc_ref.get()
                    )
                    st.experimental_rerun()

            st.success("Saved", icon="✅")

    def state_to_doc(self, state: dict):
        ret = {
            field_name: deepcopy(state[field_name])
            for field_name in self.fields_to_save()
            if field_name in state
        }
        ret |= {
            StateKeys.updated_at: datetime.datetime.utcnow(),
        }

        title = state.get(StateKeys.page_title)
        notes = state.get(StateKeys.page_notes)
        if title and title.strip() != self.title.strip():
            ret[StateKeys.page_title] = title
        if notes and notes.strip() != self.preview_description(state).strip():
            ret[StateKeys.page_notes] = notes

        return ret

    def fields_to_save(self) -> [str]:
        # only save the fields in request/response
        return [
            field_name
            for model in (self.RequestModel, self.ResponseModel)
            for field_name in model.__fields__
        ] + [
            StateKeys.error_msg,
            StateKeys.run_status,
        ]

    def _examples_tab(self):
        # if StateKeys.examples_cache not in st.session_state:
        with st.spinner("Loading Examples..."):
            example_docs = db.get_collection_ref(
                document_id=self.doc_name,
                sub_collection_id=EXAMPLES_COLLECTION,
            ).get()

            def sort_key(s):
                updated_at = s.to_dict().get(
                    StateKeys.updated_at, datetime.datetime.fromtimestamp(0)
                )
                if isinstance(updated_at, str):
                    updated_at = datetime.datetime.fromisoformat(updated_at)
                return updated_at.timestamp()

            example_docs.sort(key=sort_key, reverse=True)
        # st.session_state[StateKeys.examples_cache] = example_docs
        # example_docs = st.session_state.get(StateKeys.examples_cache)

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
        run_history = st.session_state.get(StateKeys.history_cache, [])

        with st.spinner("Loading History..."):
            run_history.extend(
                db.get_collection_ref(
                    collection_id=USER_RUNS_COLLECTION,
                    document_id=uid,
                    sub_collection_id=self.doc_name,
                )
                .order_by(StateKeys.updated_at, direction="DESCENDING")
                .offset(len(run_history))
                .limit(20)
                .get()
            )

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

        # if StateKeys.history_cache not in st.session_state or st.button("Load More"):
        # st.session_state[StateKeys.history_cache] = run_history
        # st.experimental_rerun()

    def _render_doc_example(
        self, *, allow_delete: bool, doc: dict, url: str, query_params: dict
    ):
        col1, col2 = st.columns([2, 6])

        with col1:
            st.markdown(f"""[✏️ Tweak]({url})""")
            copy_to_clipboard_button("🔗 Copy URL", value=url)

            if allow_delete:
                self._example_delete_button(**query_params)

            updated_at = doc.get("updated_at")
            if updated_at and isinstance(updated_at, datetime.datetime):
                js_dynamic_date(updated_at)

        with col2:
            title = doc.get(StateKeys.page_title)
            if title and title.strip() != self.title.strip():
                st.write("#### " + title)

            notes = doc.get(StateKeys.page_notes)
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

        example = self.example_doc_ref(example_id)

        with st.spinner("deleting..."):
            example.update({"__hidden": True})

        example_docs = st.session_state.get(StateKeys.examples_cache, [])
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
        return extract_nested_str(out)

    def fallback_preivew_image(self) -> str:
        return DEFAULT_META_IMG

    def run_as_api_tab(self):
        api_docs_url = str(
            furl(
                settings.API_BASE_URL,
                fragment_path=f"operation/{self.slug_versions[0]}",
            )
            / "docs"
        )
        st.markdown(f"### [📖 API Docs]({api_docs_url})")

        st.write("#### 📤 Example Request")

        include_all = st.checkbox("Show all fields")
        as_form_data = st.checkbox("Upload Files via Form Data")

        request_body = get_example_request_body(
            self.RequestModel, st.session_state, include_all=include_all
        )
        response_body = self.get_example_response_body(
            st.session_state, include_all=include_all
        )

        api_example_generator(self._get_current_api_url(), request_body, as_form_data)
        st.write("")

        user = st.session_state.get("_current_user")
        if hasattr(user, "_is_anonymous"):
            st.write("**Please Login to generate the `$GOOEY_API_KEY`**")
            return

        st.write("#### 🎁 Example Response")
        st.json(response_body, expanded=True)

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

        if balance <= 0:
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

    def deduct_credits(self, state: dict):
        user = state.get("_current_user")
        if not user:
            return
        # don't allow fractional pricing for now, min 1 credit
        amount = self.get_price_roundoff(state)
        db.update_user_balance(user.uid, -abs(amount), f"gooey_in_{uuid.uuid1()}")

    def get_price_roundoff(self, state: dict) -> int:
        return max(1, math.ceil(self.get_raw_price(state)))

    def get_raw_price(self, state: dict) -> float:
        return self.price

    def get_example_response_body(
        self,
        state: dict,
        include_all: bool = False,
    ) -> dict:
        example_id, run_id, uid = extract_query_params(gooey_get_query_params())
        return dict(
            id=run_id or example_id or get_random_doc_id(),
            url=self._get_current_app_url(),
            created_at=datetime.datetime.utcnow().isoformat(),
            output=get_example_request_body(
                self.ResponseModel,
                state,
                include_all=include_all,
            ),
        )

    def additional_notes(self) -> str | None:
        pass


def get_example_request_body(
    request_model: typing.Type[BaseModel],
    state: dict,
    include_all: bool = False,
) -> dict:
    return {
        field_name: state.get(field_name)
        for field_name, field in request_model.__fields__.items()
        if include_all or field.required
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
        else:
            format_exc = err_body.get("format_exc")
            if format_exc:
                print("⚡️ " + format_exc)
            err_type = err_body.get("type")
            err_str = err_body.get("str")
            if err_type and err_str:
                return f"(GPU) {err_type}: {err_str}"
        return f"(HTTP {response.status_code}) {err_body}"
    else:
        return f"{type(e).__name__}: {e}"


def is_admin():
    if "_current_user" not in st.session_state:
        return False
    current_user: UserRecord = st.session_state["_current_user"]
    email = current_user.email
    if email and email in settings.ADMIN_EMAILS:
        return True
    return False
