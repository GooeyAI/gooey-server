import datetime
import html
import inspect
import typing
import urllib
import urllib.parse
import uuid
from copy import deepcopy
from random import Random
from time import sleep
from types import SimpleNamespace

import math
import requests
import sentry_sdk
from django.utils import timezone
from enum import Enum
from fastapi import HTTPException
from firebase_admin import auth
from furl import furl
from pydantic import BaseModel
from sentry_sdk.tracing import (
    TRANSACTION_SOURCE_ROUTE,
)
from starlette.requests import Request

import gooey_ui as st
from app_users.models import AppUser, AppUserTransaction
from bots.models import SavedRun, Workflow
from daras_ai_v2 import settings
from daras_ai_v2.api_examples_widget import api_example_generator
from daras_ai_v2.copy_to_clipboard_button_widget import (
    copy_to_clipboard_button,
)
from daras_ai_v2.crypto import (
    get_random_doc_id,
)
from daras_ai_v2.db import (
    ANONYMOUS_USER_COOKIE,
)
from daras_ai_v2.grid_layout_widget import grid_layout
from daras_ai_v2.html_spinner_widget import html_spinner
from daras_ai_v2.manage_api_keys_widget import manage_api_keys
from daras_ai_v2.meta_preview_url import meta_preview_url
from daras_ai_v2.query_params import (
    gooey_get_query_params,
)
from daras_ai_v2.query_params_util import (
    extract_query_params,
    EXAMPLE_ID_QUERY_PARAM,
    RUN_ID_QUERY_PARAM,
    USER_ID_QUERY_PARAM,
)
from daras_ai_v2.send_email import send_reported_run_email
from daras_ai_v2.tabs_widget import MenuTabs
from daras_ai_v2.user_date_widgets import render_js_dynamic_dates, js_dynamic_date
from gooey_ui import realtime_clear_subs
from gooey_ui.pubsub import realtime_pull

DEFAULT_META_IMG = (
    # Small
    "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/optimized%20hp%20gif.gif"
    # "https://storage.googleapis.com/dara-c1b52.appspot.com/meta_tag_default_img.jpg"
    # Big
    # "https://storage.googleapis.com/dara-c1b52.appspot.com/meta_tag_gif.gif"
)
MAX_SEED = 4294967294
gooey_rng = Random()


SUBMIT_AFTER_LOGIN_Q = "submitafterlogin"


class RecipeRunState(Enum):
	idle = 1
	running = 2
	completed = 3
	failed = 4


class StateKeys:
    page_title = "__title"
    page_notes = "__notes"

    created_at = "created_at"
    updated_at = "updated_at"

    error_msg = "__error_msg"
    run_time = "__run_time"
    run_status = "__run_status"
    pressed_randomize = "__randomize"

    hidden = "__hidden"


class BasePage:
    title: str
    workflow: Workflow
    slug_versions: list[str]

    sane_defaults: dict = {}
    RequestModel: typing.Type[BaseModel]
    ResponseModel: typing.Type[BaseModel]

    price = settings.CREDITS_TO_DEDUCT_PER_RUN

    def __init__(
        self,
        tab: str = "",
        request: Request | SimpleNamespace = None,
        run_user: AppUser = None,
    ):
        self.tab = tab
        self.request = request
        self.run_user = run_user

    @classmethod
    def app_url(
        cls,
        example_id=None,
        run_id=None,
        uid=None,
        tab_name=None,
        query_params: dict = None,
    ) -> str:
        query_params = cls.clean_query_params(
            example_id=example_id, run_id=run_id, uid=uid
        ) | (query_params or {})
        f = furl(settings.APP_BASE_URL, query_params=query_params) / (
            cls.slug_versions[-1] + "/"
        )
        if tab_name:
            f /= tab_name + "/"
        return str(f)

    @classmethod
    def clean_query_params(cls, *, example_id, run_id, uid) -> dict:
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

    def get_tab_url(self, tab: str) -> str:
        example_id, run_id, uid = extract_query_params(gooey_get_query_params())
        return self.app_url(
            example_id=example_id,
            run_id=run_id,
            uid=uid,
            tab_name=MenuTabs.paths[tab],
        )

    def render(self):
        with sentry_sdk.configure_scope() as scope:
            scope.set_extra("base_url", self.app_url())
            scope.set_transaction_name(
                "/" + self.slug_versions[0], source=TRANSACTION_SOURCE_ROUTE
            )

        example_id, run_id, uid = extract_query_params(gooey_get_query_params())

        if st.session_state.get(StateKeys.run_status):
            channel = f"gooey-outputs/{self.slug_versions[0]}/{uid}/{run_id}"
            output = realtime_pull([channel])[0]
            if output:
                st.session_state.update(output)
        if not st.session_state.get(StateKeys.run_status):
            realtime_clear_subs()

        self._user_disabled_check()
        self._check_if_flagged()

        if st.session_state.get("show_report_workflow"):
            self.render_report_form()
            return

        st.session_state.setdefault(StateKeys.page_title, self.title)
        st.session_state.setdefault(
            StateKeys.page_notes, self.preview_description(st.session_state)
        )

        root_url = self.app_url(example_id=example_id)
        st.write(
            f'# <a style="text-decoration: none;" target="_top" href="{root_url}">{st.session_state.get(StateKeys.page_title)}</a>',
            unsafe_allow_html=True,
        )
        st.write(st.session_state.get(StateKeys.page_notes))

        try:
            selected_tab = MenuTabs.paths_reverse[self.tab]
        except KeyError:
            st.error(f"## 404 - Tab {self.tab!r} Not found")
            return

        with st.nav_tabs():
            tab_names = self.get_tabs()
            for name in tab_names:
                url = self.get_tab_url(name)
                with st.nav_item(url, active=name == selected_tab):
                    st.html(name)
        with st.nav_tab_content():
            self.render_selected_tab(selected_tab)

    def _user_disabled_check(self):
        if self.run_user and self.run_user.is_disabled:
            msg = (
                "This Gooey.AI account has been disabled for violating our [Terms of Service](/terms). "
                "Contact us at support@gooey.ai if you think this is a mistake."
            )
            st.error(msg, icon="😵")
            st.stop()

    def get_tabs(self):
        tabs = [MenuTabs.run, MenuTabs.examples, MenuTabs.run_as_api]
        if self.request.user:
            tabs.extend([MenuTabs.history])
        return tabs

    def render_selected_tab(self, selected_tab: str):
        match selected_tab:
            case MenuTabs.run:
                input_col, output_col = st.columns([3, 2], gap="medium")
                with input_col:
                    submitted = self._render_input_col()
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
                render_js_dynamic_dates()

            case MenuTabs.history:
                self._history_tab()
                render_js_dynamic_dates()

            case MenuTabs.run_as_api:
                self.run_as_api_tab()

    def render_related_workflows(self):
        page_clses = self.related_workflows()
        if not page_clses:
            return

        with st.link(to="/explore/"):
            st.html("<h2>Related Workflows</h2>")

        def _render(page_cls):
            page = page_cls()
            state = page_cls().recipe_doc_sr().to_dict()
            preview_image = meta_preview_url(
                page_cls().preview_image(state), page_cls().fallback_preivew_image()
            )

            with st.link(to=page.app_url()):
                st.markdown(
                    # language=html
                    f"""
<div class="w-100 mb-2" style="height:150px; background-image: url({preview_image}); background-size:cover; background-position-x:center; background-position-y:30%; background-repeat:no-repeat;"></div>
                    """
                )
                st.markdown(f"###### {page.title}")
            st.caption(page.preview_description(state))

        grid_layout(4, page_clses, _render)

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
            if not reason_for_report:
                st.error("Reason for report cannot be empty")
                return

            example_id, run_id, uid = extract_query_params(gooey_get_query_params())

            send_reported_run_email(
                user=self.request.user,
                run_uid=uid,
                url=self._get_current_app_url(),
                recipe_name=self.title,
                report_type=report_type,
                reason_for_report=reason_for_report,
                error_msg=st.session_state.get(StateKeys.error_msg),
            )

            if report_type == inappropriate_radio_text:
                self.update_flag_for_run(run_id=run_id, uid=uid, is_flagged=True)

            # st.success("Reported.")
            st.session_state["show_report_workflow"] = False
            st.experimental_rerun()

    def _check_if_flagged(self):
        if not st.session_state.get("is_flagged"):
            return

        st.error("### This Content has been Flagged")

        if self.is_current_user_admin():
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

    def get_sr_from_query_params_dict(self, query_params) -> SavedRun:
        example_id, run_id, uid = extract_query_params(query_params)
        return self.get_sr_from_query_params(example_id, run_id, uid)

    @classmethod
    def get_sr_from_query_params(
        cls, example_id: str, run_id: str, uid: str
    ) -> SavedRun:
        try:
            if run_id and uid:
                sr = cls.run_doc_sr(run_id, uid)
            elif example_id:
                sr = cls.example_doc_sr(example_id)
            else:
                sr = cls.recipe_doc_sr()
            return sr
        except SavedRun.DoesNotExist:
            raise HTTPException(status_code=404)

    @classmethod
    def recipe_doc_sr(cls) -> SavedRun:
        return SavedRun.objects.get_or_create(
            workflow=cls.workflow,
            run_id__isnull=True,
            uid__isnull=True,
            example_id__isnull=True,
        )[0]

    @classmethod
    def run_doc_sr(
        cls, run_id: str, uid: str, create: bool = False, parent: SavedRun = None
    ) -> SavedRun:
        config = dict(workflow=cls.workflow, uid=uid, run_id=run_id)
        if create:
            return SavedRun.objects.get_or_create(
                **config, defaults=dict(parent=parent)
            )[0]
        else:
            return SavedRun.objects.get(**config)

    @classmethod
    def example_doc_sr(cls, example_id: str, create: bool = False) -> SavedRun:
        config = dict(workflow=cls.workflow, example_id=example_id)
        if create:
            return SavedRun.objects.get_or_create(**config)[0]
        else:
            return SavedRun.objects.get(**config)

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

    def render_author(self):
        if not self.run_user or (
            not self.run_user.photo_url and not self.run_user.display_name
        ):
            return

        html = "<div style='display:flex; align-items:center; padding-bottom:16px'>"
        if self.run_user.photo_url:
            html += f"""
                <img style="width:38px; height:38px;border-radius:50%; pointer-events: none;" src="{self.run_user.photo_url}">
                <div style="width:8px;"></div>
            """
        if self.run_user.display_name:
            html += f"<div>{self.run_user.display_name}</div>"
        html += "</div>"

        if self.is_current_user_admin():
            linkto = lambda: st.link(
                to=self.app_url(
                    tab_name=MenuTabs.paths[MenuTabs.history],
                    query_params={"uid": self.run_user.uid},
                )
            )
        else:
            linkto = st.dummy

        with linkto():
            st.html(html)

    def get_credits_click_url(self):
        if self.request.user and self.request.user.is_anonymous:
            return "/pricing/"
        else:
            return "/account/"

    def get_submit_container_props(self):
        return dict(className="position-sticky bottom-0 bg-white")

    def render_submit_button(self, key="--submit-1"):
        with st.div(**self.get_submit_container_props()):
            st.write("---")
            col1, col2 = st.columns([2, 1], responsive=False)
            col2.node.props[
                "className"
            ] += " d-flex justify-content-end align-items-center"
            with col1:
                st.caption(
                    f"Run cost = [{self.get_price_roundoff(st.session_state)} credits]({self.get_credits_click_url()}) \\\n"
                    f"_By submitting, you agree to Gooey.AI's [terms](https://gooey.ai/terms) & [privacy policy](https://gooey.ai/privacy)._ ",
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
                st.error(e)
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
            f"**🙋🏽‍♀️ Need more help? [Join our Discord]({settings.DISCORD_INVITE_URL})**"
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
        # initialize request and response
        request = self.RequestModel.parse_obj(state)
        response = self.ResponseModel.construct()

        # run the recipe
        gen = self.run_v2(request, response)
        while True:
            try:
                val = next(gen)
            except StopIteration:
                break
            finally:
                state.update(response.dict())
            yield val

        # validate the response if successful
        self.ResponseModel.validate(response)

    def run_v2(
        self, request: BaseModel, response: BaseModel
    ) -> typing.Iterator[str | None]:
        raise NotImplementedError

    def _render_report_button(self):
        example_id, run_id, uid = extract_query_params(gooey_get_query_params())
        # only logged in users can report a run (but not explamples/default runs)
        if not (self.request.user and run_id and uid):
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

        with st.div(className="d-flex gap-1"):
            with st.div(className="flex-grow-1"):
                st.text_input(
                    "recipe url",
                    label_visibility="collapsed",
                    disabled=True,
                    value=url.split("://")[1].rstrip("/"),
                )
            copy_to_clipboard_button(
                "🔗 Copy URL",
                value=url,
                style="height: 3.2rem",
            )

    def _get_current_app_url(self) -> str | None:
        example_id, run_id, uid = extract_query_params(gooey_get_query_params())
        return self.app_url(example_id, run_id, uid)

    def _get_current_api_url(self) -> furl | None:
        example_id, run_id, uid = extract_query_params(gooey_get_query_params())
        return self.api_url(example_id, run_id, uid)

    def update_flag_for_run(self, run_id: str, uid: str, is_flagged: bool):
        ref = self.run_doc_sr(uid=uid, run_id=run_id)
        ref.is_flagged = is_flagged
        ref.save(update_fields=["is_flagged"])
        st.session_state["is_flagged"] = is_flagged

    def _render_input_col(self):
        self.render_author()
        self.render_form_v2()
        with st.expander("⚙️ Settings"):
            self.render_settings()
            st.write("---")
            st.write("##### 🖌️ Personalize")
            st.text_input("Title", key=StateKeys.page_title)
            st.text_area("Notes", key=StateKeys.page_notes)
        submitted = self.render_submit_button()
        return submitted

    def get_run_state(
        self,
    ) -> RecipeRunState:
        if st.session_state.get(StateKeys.run_status):
            return RecipeRunState.running
        elif st.session_state.get(StateKeys.error_msg):
            return RecipeRunState.failed
        elif st.session_state.get(StateKeys.run_time):
            return RecipeRunState.completed
        else:
            # when user is at a recipe root, and not running anything
            return RecipeRunState.idle

    def _render_output_col(self, submitted: bool):
        assert inspect.isgeneratorfunction(self.run)

        if st.session_state.get(StateKeys.pressed_randomize):
            st.session_state["seed"] = int(gooey_rng.randrange(MAX_SEED))
            st.session_state.pop(StateKeys.pressed_randomize, None)
            submitted = True

        if submitted or self.should_submit_after_login():
            self.on_submit()

        self._render_before_output()

        run_state = self.get_run_state()
        match run_state:
            case RecipeRunState.completed:
                self._render_completed_output()
            case RecipeRunState.failed:
                self._render_failed_output()
            case RecipeRunState.running:
                self._render_running_output()
            case RecipeRunState.idle:
                pass

        # render outputs
        self.render_output()

        if run_state != "waiting":
            self._render_after_output()

    def _render_completed_output(self):
        run_time = st.session_state.get(StateKeys.run_time, 0)
        st.success(f"Success! Run Time: `{run_time:.2f}` seconds.")

    def _render_failed_output(self):
        err_msg = st.session_state.get(StateKeys.error_msg)
        st.error(err_msg)

    def _render_running_output(self):
        run_status = st.session_state.get(StateKeys.run_status)
        st.caption("Your changes are saved in the above URL. Save it for later!")
        html_spinner(run_status)
        self.render_extra_waiting_output()

    def render_extra_waiting_output(self):
        estimated_run_time = self.estimate_run_duration()
        if not estimated_run_time:
            return
        if created_at := st.session_state.get("created_at"):
            if isinstance(created_at, datetime.datetime):
                start_time = created_at
            else:
                start_time = datetime.datetime.fromisoformat(created_at)
            with st.countdown_timer(
                end_time=start_time + datetime.timedelta(seconds=estimated_run_time),
                delay_text="Sorry for the wait. Your run is taking longer than we expected.",
            ):
                if self.is_current_user_owner() and self.request.user.email:
                    st.write(
                        f"""We'll email **{self.request.user.email}** when your workflow is done."""
                    )
                st.write(
                    f"""In the meantime, check out [🚀 Examples]({self.get_tab_url(MenuTabs.examples)})
                      for inspiration."""
                )

    def estimate_run_duration(self) -> int | None:
        pass

    def on_submit(self):
        example_id, run_id, uid = self.create_new_run()
        if settings.CREDITS_TO_DEDUCT_PER_RUN and not self.check_credits():
            st.session_state[StateKeys.run_status] = None
            st.session_state[StateKeys.error_msg] = self.generate_credit_error_message(
                example_id, run_id, uid
            )
            self.run_doc_sr(run_id, uid).set(self.state_to_doc(st.session_state))
        else:
            self.call_runner_task(example_id, run_id, uid)
        raise QueryParamsRedirectException(
            self.clean_query_params(example_id=example_id, run_id=run_id, uid=uid)
        )

    def should_submit_after_login(self) -> bool:
        return (
            st.get_query_params().get(SUBMIT_AFTER_LOGIN_Q)
            and self.request
            and self.request.user
            and not self.request.user.is_anonymous
        )

    def create_new_run(self):
        st.session_state[StateKeys.run_status] = "Starting..."
        st.session_state.pop(StateKeys.error_msg, None)
        st.session_state.pop(StateKeys.run_time, None)
        self._setup_rng_seed()
        self.clear_outputs()

        assert self.request, "request is not set for current session"
        if self.request.user:
            uid = self.request.user.uid
        else:
            uid = auth.create_user().uid
            self.request.scope["user"] = AppUser.objects.create(
                uid=uid, is_anonymous=True, balance=settings.ANON_USER_FREE_CREDITS
            )
            self.request.session[ANONYMOUS_USER_COOKIE] = dict(uid=uid)

        run_id = get_random_doc_id()

        parent_example_id, parent_run_id, parent_uid = extract_query_params(
            gooey_get_query_params()
        )
        parent = self.get_sr_from_query_params(
            parent_example_id, parent_run_id, parent_uid
        )

        self.run_doc_sr(run_id, uid, create=True, parent=parent).set(
            self.state_to_doc(st.session_state)
        )

        return parent_example_id, run_id, uid

    def call_runner_task(self, example_id, run_id, uid, is_api_call=False):
        from celeryapp.tasks import gui_runner

        return gui_runner.delay(
            page_cls=self.__class__,
            user_id=self.request.user.id,
            run_id=run_id,
            uid=uid,
            state=st.session_state,
            channel=f"gooey-outputs/{self.slug_versions[0]}/{uid}/{run_id}",
            query_params=self.clean_query_params(
                example_id=example_id, run_id=run_id, uid=uid
            ),
            is_api_call=is_api_call,
        )

    def generate_credit_error_message(self, example_id, run_id, uid) -> str:
        account_url = furl(settings.APP_BASE_URL) / "account/"
        if self.request.user.is_anonymous:
            account_url.query.params["next"] = self.app_url(
                example_id, run_id, uid, query_params={SUBMIT_AFTER_LOGIN_Q: "1"}
            )
            # language=HTML
            error_msg = f"""
<p>
Doh! <a href="{account_url}" target="_top">Please login</a> to run more Gooey.AI workflows.
</p>

You’ll receive {settings.LOGIN_USER_FREE_CREDITS} Credits when you sign up via your phone #, Google, Apple or GitHub account 
and can <a href="/pricing/" target="_blank">purchase more</a> for $1/100 Credits.
            """
        else:
            # language=HTML
            error_msg = f"""
<p>
Doh! You’re out of Gooey.AI credits.
</p>

<p>
Please <a href="{account_url}" target="_blank">buy more</a> to run more workflows.
</p>

We’re always on <a href="{settings.DISCORD_INVITE_URL}" target="_blank">discord</a> if you’ve got any questions.
            """
        return error_msg

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
        col1, col2, col3 = st.columns([1, 1, 1], responsive=False)
        col2.node.props[
            "className"
        ] += " d-flex justify-content-center align-items-center"
        col3.node.props["className"] += " d-flex justify-content-end align-items-center"
        if "seed" in self.RequestModel.schema_json():
            seed = st.session_state.get("seed")
            with col1:
                st.caption(f"*Seed\\\n`{seed}`*")
            with col2:
                randomize = st.button("♻️ Regenerate")
                if randomize:
                    st.session_state[StateKeys.pressed_randomize] = True
                    st.experimental_rerun()
        with col3:
            self._render_report_button()

    def _render_save_options(self):
        if not self.is_current_user_admin():
            return

        parent_example_id, parent_run_id, parent_uid = extract_query_params(
            gooey_get_query_params()
        )
        current_sr = self.get_sr_from_query_params(
            parent_example_id, parent_run_id, parent_uid
        )

        with st.expander("🛠️ Admin Options"):
            sr_to_save = None

            if st.button("⭐️ Save Workflow"):
                sr_to_save = self.recipe_doc_sr()

            if st.button("🔖 Create new Example"):
                sr_to_save = self.example_doc_sr(get_random_doc_id(), create=True)

            if parent_example_id:
                if st.button("💾 Save this Example"):
                    sr_to_save = self.example_doc_sr(parent_example_id)

            if current_sr.example_id:
                hidden = st.session_state.get(StateKeys.hidden)
                if st.button("👁️ Make Public" if hidden else "🙈️ Hide"):
                    self.set_hidden(
                        example_id=current_sr.example_id,
                        doc=st.session_state,
                        hidden=not hidden,
                    )

            if sr_to_save:
                if current_sr != sr_to_save:  # ensure parent != child
                    sr_to_save.parent = current_sr
                sr_to_save.set(self.state_to_doc(st.session_state))
                ## TODO: pass the success message to the redirect
                # st.success("Saved", icon="✅")
                raise QueryParamsRedirectException(
                    dict(example_id=sr_to_save.example_id)
                )

            if current_sr.parent:
                st.write(f"Parent: {current_sr.parent.get_app_url()}")

    def state_to_doc(self, state: dict):
        ret = {
            field_name: deepcopy(state[field_name])
            for field_name in self.fields_to_save()
            if field_name in state
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
            StateKeys.run_time,
        ]

    def _examples_tab(self):
        allow_delete = self.is_current_user_admin()

        def _render(sr: SavedRun):
            url = str(
                furl(
                    self.app_url(), query_params={EXAMPLE_ID_QUERY_PARAM: sr.example_id}
                )
            )
            self._render_doc_example(
                allow_delete=allow_delete,
                doc=sr.to_dict(),
                url=url,
                query_params=dict(example_id=sr.example_id),
            )

        example_runs = SavedRun.objects.filter(
            workflow=self.workflow,
            hidden=False,
            example_id__isnull=False,
        )[:50]

        grid_layout(3, example_runs, _render)

    def _history_tab(self):
        assert self.request, "request must be set to render history tab"
        if not self.request.user:
            redirect_url = furl(
                "/login", query_params={"next": furl(self.request.url).set(origin=None)}
            )
            raise RedirectException(str(redirect_url))
        uid = self.request.user.uid
        if self.is_current_user_admin():
            uid = self.request.query_params.get("uid", uid)

        before = gooey_get_query_params().get("updated_at__lt", None)
        if before:
            before = datetime.datetime.fromisoformat(before)
        else:
            before = timezone.now()
        run_history = list(
            SavedRun.objects.filter(
                workflow=self.workflow,
                uid=uid,
                updated_at__lt=before,
            )[:25]
        )
        if not run_history:
            st.write("No history yet")
            return

        def _render(sr: SavedRun):
            url = str(
                furl(
                    self.app_url(),
                    query_params={
                        RUN_ID_QUERY_PARAM: sr.run_id,
                        USER_ID_QUERY_PARAM: uid,
                    },
                )
            )

            self._render_doc_example(
                allow_delete=False,
                doc=sr.to_dict(),
                url=url,
                query_params=dict(run_id=sr.run_id, uid=uid),
            )

        grid_layout(3, run_history, _render)

        next_url = (
            furl(self._get_current_app_url(), query_params=self.request.query_params)
            / MenuTabs.paths[MenuTabs.history]
            / "/"
        )
        next_url.query.params.set(
            "updated_at__lt", run_history[-1].to_dict()["updated_at"]
        )
        with st.link(to=str(next_url)):
            st.html(
                # language=HTML
                f"""<button type="button" class="btn btn-theme">Load More</button>"""
            )

    def _render_doc_example(
        self, *, allow_delete: bool, doc: dict, url: str, query_params: dict
    ):
        with st.link(to=url):
            st.html(
                # language=HTML
                f"""<button type="button" class="btn btn-theme">✏️ Tweak</button>"""
            )
        copy_to_clipboard_button("🔗 Copy URL", value=url)
        if allow_delete:
            self._example_delete_button(**query_params, doc=doc)

        updated_at = doc.get("updated_at")
        if updated_at and isinstance(updated_at, datetime.datetime):
            js_dynamic_date(updated_at)

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

    def _example_delete_button(self, example_id, doc):
        pressed_delete = st.button(
            "🙈️ Hide",
            key=f"delete_example_{example_id}",
            style={"color": "red"},
        )
        if not pressed_delete:
            return
        self.set_hidden(example_id=example_id, doc=doc, hidden=True)

    def set_hidden(self, *, example_id, doc, hidden: bool):
        sr = self.example_doc_sr(example_id)

        with st.spinner("Hiding..."):
            doc[StateKeys.hidden] = hidden
            sr.hidden = hidden
            sr.save(update_fields=["hidden", "updated_at"])

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

        st.markdown(
            f'📖 To learn more, take a look at our <a href="{api_docs_url}" target="_blank">complete API</a>'
        )

        st.write("#### 📤 Example Request")

        include_all = st.checkbox("##### Show all fields")
        as_async = st.checkbox("##### Run Async")
        as_form_data = st.checkbox("##### Upload Files via Form Data")

        request_body = get_example_request_body(
            self.RequestModel, st.session_state, include_all=include_all
        )
        response_body = self.get_example_response_body(
            st.session_state, as_async=as_async, include_all=include_all
        )

        api_example_generator(
            api_url=self._get_current_api_url(),
            request_body=request_body,
            as_form_data=as_form_data,
            as_async=as_async,
        )
        st.write("")

        st.write("#### 🎁 Example Response")
        st.json(response_body, expanded=True)

        if not self.request.user or self.request.user.is_anonymous:
            st.write("**Please Login to generate the `$GOOEY_API_KEY`**")
            return

        st.write("---")
        with st.tag("a", id="api-keys"):
            st.write("### 🔐 API keys")

        manage_api_keys(self.request.user)

    def check_credits(self) -> bool:
        assert self.request, "request must be set to check credits"
        assert self.request.user, "request.user must be set to check credits"
        return self.request.user.balance >= self.get_price_roundoff(st.session_state)

    def deduct_credits(self, state: dict) -> tuple[AppUserTransaction, int]:
        assert (
            self.request and self.request.user
        ), "request.user must be set to deduct credits"

        amount = self.get_price_roundoff(state)
        txn = self.request.user.add_balance(-amount, f"gooey_in_{uuid.uuid1()}")
        return txn, amount

    def get_price_roundoff(self, state: dict) -> int:
        # don't allow fractional pricing for now, min 1 credit
        return max(1, math.ceil(self.get_raw_price(state)))

    def get_raw_price(self, state: dict) -> float:
        return self.price

    def get_example_response_body(
        self,
        state: dict,
        as_async: bool = False,
        include_all: bool = False,
    ) -> dict:
        run_id = get_random_doc_id()
        created_at = st.session_state.get(
            StateKeys.created_at, datetime.datetime.utcnow().isoformat()
        )
        web_url = self.app_url(
            run_id=run_id,
            uid=self.request.user and self.request.user.uid,
        )
        if as_async:
            return dict(
                run_id=run_id,
                web_url=web_url,
                created_at=created_at,
                run_time_sec=st.session_state.get(StateKeys.run_time, 0),
                status="completed",
                output=get_example_request_body(
                    self.ResponseModel, state, include_all=include_all
                ),
            )
        else:
            return dict(
                id=run_id,
                url=web_url,
                created_at=created_at,
                output=get_example_request_body(
                    self.ResponseModel, state, include_all=include_all
                ),
            )

    def additional_notes(self) -> str | None:
        pass

    def is_current_user_admin(self) -> bool:
        if not self.request or not self.request.user:
            return False
        email = self.request.user.email
        return email and email in settings.ADMIN_EMAILS

    def is_current_user_paying(self) -> bool:
        return bool(self.request and self.request.user and self.request.user.is_paying)

    def is_current_user_owner(self) -> bool:
        """
        Did the current user create this run?
        """
        return bool(
            self.request
            and self.request.user
            and self.run_user
            and self.request.user.uid == self.run_user.uid
        )


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
            err_str = response.text
        else:
            format_exc = err_body.get("format_exc")
            if format_exc:
                print("⚡️ " + format_exc)
            err_type = err_body.get("type")
            err_str = err_body.get("str")
            if err_type and err_str:
                return f"(GPU) {err_type}: {err_str}"
            err_str = str(err_body)
        return f"(HTTP {response.status_code}) {html.escape(err_str[:1000])}"
    else:
        return f"{type(e).__name__}: {e}"


class RedirectException(Exception):
    def __init__(self, url, status_code=302):
        self.url = url
        self.status_code = status_code


class QueryParamsRedirectException(RedirectException):
    def __init__(self, query_params: dict, status_code=303):
        query_params = {k: v for k, v in query_params.items() if v is not None}
        url = "?" + urllib.parse.urlencode(query_params)
        super().__init__(url, status_code)
