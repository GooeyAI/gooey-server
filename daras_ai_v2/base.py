import datetime
import html
import inspect
import math
import typing
import urllib
import urllib.parse
import uuid
from copy import deepcopy
from enum import Enum
from itertools import pairwise
from random import Random
from time import sleep
from types import SimpleNamespace

import sentry_sdk
from django.utils import timezone
from django.utils.text import slugify
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
from bots.models import (
    SavedRun,
    PublishedRun,
    PublishedRunVersion,
    PublishedRunVisibility,
    Workflow,
)
from daras_ai_v2 import settings
from daras_ai_v2.api_examples_widget import api_example_generator
from daras_ai_v2.breadcrumbs import render_breadcrumbs, get_title_breadcrumbs
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
)
from daras_ai_v2.send_email import send_reported_run_email
from daras_ai_v2.tabs_widget import MenuTabs
from daras_ai_v2.user_date_widgets import (
    render_js_dynamic_dates,
    re_render_js_dynamic_dates,
    js_dynamic_date,
)
from gooey_ui import realtime_clear_subs
from gooey_ui.components.modal import Modal
from gooey_ui.pubsub import realtime_pull

DEFAULT_META_IMG = (
    # Small
    "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/b0f328d0-93f7-11ee-bd89-02420a0001cc/Main.jpg.png"
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

    explore_image: str = None

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
        f = (
            furl(settings.APP_BASE_URL, query_params=query_params)
            / cls.slug_versions[-1]
        )
        if example_id := query_params.get("example_id"):
            pr = cls.get_published_run(published_run_id=example_id)
            if pr and pr.title:
                f /= slugify(pr.title)
        if tab_name:
            f /= tab_name
        f /= "/"  # keep trailing slash
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

    def setup_render(self):
        with sentry_sdk.configure_scope() as scope:
            scope.set_extra("base_url", self.app_url())
            scope.set_transaction_name(
                "/" + self.slug_versions[0], source=TRANSACTION_SOURCE_ROUTE
            )

    def refresh_state(self):
        _, run_id, uid = extract_query_params(gooey_get_query_params())
        channel = self.realtime_channel_name(run_id, uid)
        output = realtime_pull([channel])[0]
        if output:
            st.session_state.update(output)

    def render(self):
        self.setup_render()

        if self.get_run_state(st.session_state) == RecipeRunState.running:
            self.refresh_state()
        else:
            realtime_clear_subs()

        self._user_disabled_check()
        self._check_if_flagged()

        if st.session_state.get("show_report_workflow"):
            self.render_report_form()
            return

        self._render_header()

        self._render_tab_menu(selected_tab=self.tab)
        with st.nav_tab_content():
            self.render_selected_tab(self.tab)

    def _render_tab_menu(self, selected_tab: str):
        assert selected_tab in MenuTabs.paths

        with st.nav_tabs():
            for name in self.get_tabs():
                url = self.get_tab_url(name)
                with st.nav_item(url, active=name == selected_tab):
                    st.html(name)

    def _render_header(self):
        current_run = self.get_current_sr()
        published_run = self.get_current_published_run()
        is_root_example = (
            published_run
            and published_run.is_root()
            and published_run.saved_run == current_run
        )
        tbreadcrumbs = get_title_breadcrumbs(
            self, current_run, published_run, tab=self.tab
        )

        with st.div(className="d-flex justify-content-between mt-4"):
            with st.div(className="d-lg-flex d-block align-items-center"):
                if not tbreadcrumbs.has_breadcrumbs() and not self.run_user:
                    self._render_title(tbreadcrumbs.h1_title)

                if tbreadcrumbs:
                    with st.tag("div", className="me-3 mb-1 mb-lg-0 py-2 py-lg-0"):
                        render_breadcrumbs(
                            tbreadcrumbs,
                            is_api_call=(
                                current_run.is_api_call and self.tab == MenuTabs.run
                            ),
                        )

                author = self.run_user or current_run.get_creator()
                if not is_root_example:
                    self.render_author(
                        author,
                        show_as_link=self.is_current_user_admin(),
                    )

            with st.div(className="d-flex align-items-center"):
                can_user_edit_run = self.is_current_user_admin() or (
                    self.request
                    and self.request.user
                    and current_run.uid == self.request.user.uid
                )
                has_unpublished_changes = (
                    published_run
                    and published_run.saved_run != current_run
                    and self.request
                    and self.request.user
                    and published_run.created_by == self.request.user
                )

                if can_user_edit_run and has_unpublished_changes:
                    self._render_unpublished_changes_indicator()

                with st.div(className="d-flex align-items-start right-action-icons"):
                    st.html(
                        """
                    <style>
                    .right-action-icons .btn {
                        padding: 6px;
                    }
                    </style>
                    """
                    )

                    if published_run and can_user_edit_run:
                        self._render_published_run_buttons(
                            current_run=current_run,
                            published_run=published_run,
                        )

                    self._render_social_buttons(show_button_text=not can_user_edit_run)

        with st.div():
            if tbreadcrumbs.has_breadcrumbs() or self.run_user:
                # only render title here if the above row was not empty
                self._render_title(tbreadcrumbs.h1_title)
            if published_run and published_run.notes:
                st.write(published_run.notes)
            elif is_root_example:
                st.write(self.preview_description(current_run.to_dict()))

    def _render_title(self, title: str):
        st.write(f"# {title}")

    def _render_unpublished_changes_indicator(self):
        with st.div(
            className="d-none d-lg-flex h-100 align-items-center text-muted ms-2"
        ):
            with st.tag("span", className="d-inline-block"):
                st.html("Unpublished changes")

    def _render_social_buttons(self, show_button_text: bool = False):
        button_text = (
            '<span class="d-none d-lg-inline"> Copy Link</span>'
            if show_button_text
            else ""
        )

        copy_to_clipboard_button(
            f'<i class="fa-regular fa-link"></i>{button_text}',
            value=self._get_current_app_url(),
            type="secondary",
            className="mb-0 ms-lg-2",
        )

    def _render_published_run_buttons(
        self,
        *,
        current_run: SavedRun,
        published_run: PublishedRun,
    ):
        is_update_mode = (
            self.is_current_user_admin()
            or published_run.created_by == self.request.user
        )

        with st.div(className="d-flex justify-content-end"):
            st.html(
                """
                <style>
                    .save-button-menu .gui-input label p { color: black; }
                    .visibility-radio .gui-input {
                        margin-bottom: 0;
                    }
                    .published-options-menu {
                        z-index: 1;
                    }
                </style>
                """
            )

            pressed_options = is_update_mode and st.button(
                '<i class="fa-regular fa-ellipsis"></i>',
                className="mb-0 ms-lg-2",
                type="tertiary",
            )
            options_modal = Modal("Options", key="published-run-options-modal")
            if pressed_options:
                options_modal.open()
            if options_modal.is_open():
                with options_modal.container(style={"min-width": "min(300px, 100vw)"}):
                    self._render_options_modal(
                        current_run=current_run,
                        published_run=published_run,
                        modal=options_modal,
                    )

            save_icon = '<i class="fa-regular fa-floppy-disk"></i>'
            if is_update_mode:
                save_text = "Update"
            else:
                save_text = "Save"
            pressed_save = st.button(
                f'{save_icon} <span class="d-none d-lg-inline">{save_text}</span>',
                className="mb-0 ms-lg-2 px-lg-4",
                type="primary",
            )
            publish_modal = Modal("Publish to", key="publish-modal")
            if pressed_save:
                publish_modal.open()
            if publish_modal.is_open():
                with publish_modal.container(style={"min-width": "min(500px, 100vw)"}):
                    self._render_publish_modal(
                        current_run=current_run,
                        published_run=published_run,
                        modal=publish_modal,
                        is_update_mode=is_update_mode,
                    )

    def _render_publish_modal(
        self,
        *,
        current_run: SavedRun,
        published_run: PublishedRun,
        modal: Modal,
        is_update_mode: bool = False,
    ):
        if published_run.is_root() and self.is_current_user_admin():
            with st.div(className="text-danger"):
                st.write(
                    "###### You're about to update the root workflow as an admin. "
                )
            st.html(
                'If you want to create a new example, press <i class="fa-regular fa-ellipsis"></i> and "Duplicate" instead.'
            )
            published_run_visibility = PublishedRunVisibility.PUBLIC
        else:
            with st.div(className="visibility-radio"):
                options = {
                    str(enum.value): enum.help_text() for enum in PublishedRunVisibility
                }
                published_run_visibility = PublishedRunVisibility(
                    int(
                        st.radio(
                            "",
                            options=options,
                            format_func=options.__getitem__,
                            value=str(published_run.visibility),
                        )
                    )
                )
                st.radio(
                    "",
                    options=[
                        '<span class="text-muted">Anyone at my org (coming soon)</span>'
                    ],
                    disabled=True,
                    checked_by_default=False,
                )

        with st.div(className="mt-4"):
            if is_update_mode:
                title = published_run.title or self.title
            else:
                recipe_title = self.get_root_published_run().title or self.title
                if self.request.user.display_name:
                    username = self.request.user.display_name + "'s"
                elif self.request.user.email:
                    username = self.request.user.email.split("@")[0] + "'s"
                else:
                    username = "My"
                title = f"{username} {recipe_title}"
            published_run_title = st.text_input(
                "##### Title",
                key="published_run_title",
                value=title,
            )
            published_run_notes = st.text_area(
                "##### Notes",
                key="published_run_notes",
                value=(
                    published_run.notes
                    or self.preview_description(st.session_state)
                    or ""
                ),
            )

        with st.div(className="mt-4 d-flex justify-content-center"):
            pressed_save = st.button(
                f'<i class="fa-regular fa-floppy-disk"></i> Save',
                className="px-4",
                type="primary",
            )

        self._render_admin_options(current_run, published_run)

        if not pressed_save:
            return

        is_root_published_run = is_update_mode and published_run.is_root()
        if not is_root_published_run:
            try:
                self._validate_published_run_title(published_run_title)
            except TitleValidationError as e:
                st.error(str(e))
                return

        if is_update_mode:
            updates = dict(
                saved_run=current_run,
                title=published_run_title.strip(),
                notes=published_run_notes.strip(),
                visibility=published_run_visibility,
            )
            if not self._has_published_run_changed(
                published_run=published_run, **updates
            ):
                st.error("No changes to publish", icon="⚠️")
                return
            published_run.add_version(user=self.request.user, **updates)
        else:
            published_run = self.create_published_run(
                published_run_id=get_random_doc_id(),
                saved_run=current_run,
                user=self.request.user,
                title=published_run_title.strip(),
                notes=published_run_notes.strip(),
                visibility=published_run_visibility,
            )
        force_redirect(published_run.get_app_url())

    def _validate_published_run_title(self, title: str):
        if slugify(title) in settings.DISALLOWED_TITLE_SLUGS:
            raise TitleValidationError(
                "This title is not allowed. Please choose a different title."
            )
        elif title.strip() == self.get_recipe_title():
            raise TitleValidationError(
                "Please choose a different title for your published run."
            )
        elif title.strip() == "":
            raise TitleValidationError("Title cannot be empty.")

    def _has_published_run_changed(
        self,
        *,
        published_run: PublishedRun,
        saved_run: SavedRun,
        title: str,
        notes: str,
        visibility: PublishedRunVisibility,
    ):
        return (
            published_run.title != title
            or published_run.notes != notes
            or published_run.visibility != visibility
            or published_run.saved_run != saved_run
        )

    def _render_options_modal(
        self,
        *,
        current_run: SavedRun,
        published_run: PublishedRun,
        modal: Modal,
    ):
        is_latest_version = published_run.saved_run == current_run

        with st.div(className="mt-4"):
            duplicate_button = None
            save_as_new_button = None
            duplicate_icon = save_as_new_icon = '<i class="fa-regular fa-copy"></i>'
            if is_latest_version:
                duplicate_button = st.button(
                    f"{duplicate_icon} Duplicate", className="w-100"
                )
            else:
                save_as_new_button = st.button(
                    f"{save_as_new_icon} Save as New", className="w-100"
                )
            delete_button = not published_run.is_root() and st.button(
                f'<i class="fa-regular fa-trash"></i> Delete',
                className="w-100 text-danger",
            )

        if duplicate_button:
            duplicate_pr = self.duplicate_published_run(
                published_run,
                title=f"{published_run.title} (Copy)",
                notes=published_run.notes,
                visibility=PublishedRunVisibility(PublishedRunVisibility.UNLISTED),
            )
            raise QueryParamsRedirectException(
                query_params=dict(example_id=duplicate_pr.published_run_id),
            )

        if save_as_new_button:
            new_pr = self.create_published_run(
                published_run_id=get_random_doc_id(),
                saved_run=current_run,
                user=self.request.user,
                title=f"{published_run.title} (Copy)",
                notes=published_run.notes,
                visibility=PublishedRunVisibility(PublishedRunVisibility.UNLISTED),
            )
            raise QueryParamsRedirectException(
                query_params=dict(example_id=new_pr.published_run_id)
            )

        with st.div(className="mt-4"):
            st.write("#### Version History", className="mb-4")
            self._render_version_history()

        confirm_delete_modal = Modal("Confirm Delete", key="confirm-delete-modal")
        if delete_button:
            confirm_delete_modal.open()
        if confirm_delete_modal.is_open():
            modal.empty()
            with confirm_delete_modal.container():
                self._render_confirm_delete_modal(
                    published_run=published_run,
                    modal=confirm_delete_modal,
                )

    def _render_confirm_delete_modal(
        self,
        *,
        published_run: PublishedRun,
        modal: Modal,
    ):
        st.write(
            "Are you sure you want to delete this published run? "
            f"_({published_run.title})_"
        )
        st.caption("This will also delete all the associated versions.")
        with st.div(className="d-flex"):
            confirm_button = st.button(
                '<span class="text-danger">Confirm</span>',
                type="secondary",
                className="w-100",
            )
            cancel_button = st.button(
                "Cancel",
                type="secondary",
                className="w-100",
            )

        if confirm_button:
            published_run.delete()
            raise QueryParamsRedirectException(query_params={})

        if cancel_button:
            modal.close()

    def _render_admin_options(self, current_run: SavedRun, published_run: PublishedRun):
        if (
            not self.is_current_user_admin()
            or published_run.is_root()
            or published_run.saved_run != current_run
        ):
            return

        with st.expander("🛠️ Admin Options"):
            st.write(
                f"This will hide/show this workflow from {self.app_url(tab_name=MenuTabs.paths[MenuTabs.examples])}  \n"
                f"(Given that you have set public visibility above)"
            )
            if st.session_state.get("--toggle-approve-example"):
                published_run.is_approved_example = (
                    not published_run.is_approved_example
                )
                published_run.save(update_fields=["is_approved_example"])
            if published_run.is_approved_example:
                btn_text = "🙈 Hide from Examples"
            else:
                btn_text = "✅ Approve as Example"
            st.button(btn_text, key="--toggle-approve-example")

            st.write("---")

            if st.checkbox("⭐️ Save as Root Workflow"):
                st.write(
                    f"Are you Sure?  \n"
                    f"This will overwrite the contents of {self.app_url()}",
                    className="text-danger",
                )
                if st.button("👌 Yes, Update the Root Workflow"):
                    root_run = self.get_root_published_run()
                    root_run.add_version(
                        user=self.request.user,
                        title=published_run.title,
                        notes=published_run.notes,
                        saved_run=published_run.saved_run,
                        visibility=PublishedRunVisibility.PUBLIC,
                    )
                    raise QueryParamsRedirectException(dict())

    @classmethod
    def get_recipe_title(cls) -> str:
        return (
            cls.get_or_create_root_published_run().title
            or cls.title
            or cls.workflow.label
        )

    def get_explore_image(self, state: dict) -> str:
        return self.explore_image or ""

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
        if self.request.user and not self.request.user.is_anonymous:
            tabs.extend([MenuTabs.saved])
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

                self.render_related_workflows()
                render_js_dynamic_dates()

            case MenuTabs.examples:
                self._examples_tab()
                render_js_dynamic_dates()

            case MenuTabs.history:
                self._history_tab()
                render_js_dynamic_dates()

            case MenuTabs.run_as_api:
                self.run_as_api_tab()

            case MenuTabs.saved:
                self._saved_tab()
                render_js_dynamic_dates()

    def _render_version_history(self):
        published_run = self.get_current_published_run()

        if published_run:
            versions = published_run.versions.all()
            first_version = versions[0]
            for version, older_version in pairwise(versions):
                first_version = older_version
                self._render_version_row(version, older_version)
            self._render_version_row(first_version, None)
            re_render_js_dynamic_dates()

    def _render_version_row(
        self,
        version: PublishedRunVersion,
        older_version: PublishedRunVersion | None,
    ):
        st.html(
            """
            <style>
            .disable-p-margin p {
                margin-bottom: 0;
            }
            </style>
            """
        )
        url = self.app_url(
            example_id=version.published_run.published_run_id,
            run_id=version.saved_run.run_id,
            uid=version.saved_run.uid,
        )
        with st.link(to=url, className="text-decoration-none"):
            with st.div(
                className="d-flex mb-4 disable-p-margin",
                style={"min-width": "min(100vw, 500px)"},
            ):
                col1 = st.div(className="me-4")
                col2 = st.div()
        with col1:
            with st.div(className="fs-5 mt-1"):
                st.html('<i class="fa-regular fa-clock"></i>')
        with col2:
            is_first_version = not older_version
            with st.div(className="fs-5 d-flex align-items-center"):
                js_dynamic_date(
                    version.created_at,
                    container=self._render_version_history_date,
                    date_options={"month": "short", "day": "numeric"},
                )
                if is_first_version:
                    with st.tag("span", className="badge bg-secondary px-3 ms-2"):
                        st.write("FIRST VERSION")
            with st.div(className="text-muted"):
                if older_version and older_version.title != version.title:
                    st.write(f"Renamed: {version.title}")
                elif not older_version:
                    st.write(version.title)
            with st.div(className="mt-1", style={"font-size": "0.85rem"}):
                self.render_author(
                    version.changed_by, image_size="18px", responsive=False
                )

    def _render_version_history_date(self, text, **props):
        with st.tag("span", **props):
            st.html(text)

    def render_related_workflows(self):
        page_clses = self.related_workflows()
        if not page_clses:
            return

        with st.link(to="/explore/"):
            st.html("<h2>Related Workflows</h2>")

        def _render(page_cls: typing.Type[BasePage]):
            page = page_cls()
            root_run = page.get_root_published_run()
            state = root_run.saved_run.to_dict()
            preview_image = meta_preview_url(
                page.get_explore_image(state), page.fallback_preivew_image()
            )

            with st.link(to=page.app_url()):
                st.html(
                    # language=html
                    f"""
<div class="w-100 mb-2" style="height:150px; background-image: url({preview_image}); background-size:cover; background-position-x:center; background-position-y:30%; background-repeat:no-repeat;"></div>
                    """
                )
                st.markdown(f"###### {root_run.title or page.title}")
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

    @classmethod
    def get_runs_from_query_params(
        cls, example_id: str, run_id: str, uid: str
    ) -> tuple[SavedRun, PublishedRun | None]:
        if run_id and uid:
            sr = cls.run_doc_sr(run_id, uid)
            pr = sr.parent_published_run()
        else:
            pr = cls.get_published_run(published_run_id=example_id or "")
            sr = pr.saved_run
        return sr, pr

    @classmethod
    def get_current_published_run(cls) -> PublishedRun | None:
        example_id, run_id, uid = extract_query_params(gooey_get_query_params())
        return cls.get_pr_from_query_params(example_id, run_id, uid)

    @classmethod
    def get_pr_from_query_params(
        cls, example_id: str, run_id: str, uid: str
    ) -> PublishedRun | None:
        if run_id and uid:
            sr = cls.get_sr_from_query_params(example_id, run_id, uid)
            return sr.parent_published_run()
        elif example_id:
            return cls.get_published_run(published_run_id=example_id)
        else:
            return cls.get_root_published_run()

    @classmethod
    def get_root_published_run(cls) -> PublishedRun:
        return cls.get_published_run(published_run_id="")

    @classmethod
    def get_published_run(cls, *, published_run_id: str):
        return PublishedRun.objects.get(
            workflow=cls.workflow,
            published_run_id=published_run_id,
        )

    @classmethod
    def get_current_sr(cls) -> SavedRun:
        return cls.get_sr_from_query_params_dict(gooey_get_query_params())

    @classmethod
    def get_sr_from_query_params_dict(cls, query_params) -> SavedRun:
        example_id, run_id, uid = extract_query_params(query_params)
        return cls.get_sr_from_query_params(example_id, run_id, uid)

    @classmethod
    def get_sr_from_query_params(
        cls, example_id: str, run_id: str, uid: str
    ) -> SavedRun:
        try:
            if run_id and uid:
                sr = cls.run_doc_sr(run_id, uid)
            elif example_id:
                pr = cls.get_published_run(published_run_id=example_id)
                assert (
                    pr.saved_run is not None
                ), "invalid published run: without a saved run"
                sr = pr.saved_run
            else:
                sr = cls.recipe_doc_sr()
            return sr
        except (SavedRun.DoesNotExist, PublishedRun.DoesNotExist):
            raise HTTPException(status_code=404)

    @classmethod
    def get_total_runs(cls) -> int:
        # TODO: fix to also handle published run case
        return SavedRun.objects.filter(workflow=cls.workflow).count()

    @classmethod
    def get_or_create_root_published_run(cls) -> PublishedRun:
        published_run, _ = PublishedRun.objects.get_or_create(
            workflow=cls.workflow,
            published_run_id="",
            defaults={
                "saved_run": lambda: cls.run_doc_sr(run_id="", uid="", create=True),
                "created_by": None,
                "last_edited_by": None,
                "title": cls.title,
                "notes": cls().preview_description(state=cls.sane_defaults),
                "visibility": PublishedRunVisibility(PublishedRunVisibility.PUBLIC),
                "is_approved_example": True,
            },
        )
        return published_run

    @classmethod
    def recipe_doc_sr(cls, create: bool = False) -> SavedRun:
        if create:
            return cls.get_or_create_root_published_run().saved_run
        else:
            return cls.get_root_published_run().saved_run

    @classmethod
    def run_doc_sr(
        cls,
        run_id: str,
        uid: str,
        create: bool = False,
        defaults: dict = None,
    ) -> SavedRun:
        config = dict(workflow=cls.workflow, uid=uid, run_id=run_id)
        if create:
            return SavedRun.objects.get_or_create(**config, defaults=defaults)[0]
        else:
            return SavedRun.objects.get(**config)

    @classmethod
    def create_published_run(
        cls,
        *,
        published_run_id: str,
        saved_run: SavedRun,
        user: AppUser,
        title: str,
        notes: str,
        visibility: PublishedRunVisibility,
    ):
        return PublishedRun.objects.create_published_run(
            workflow=cls.workflow,
            published_run_id=published_run_id,
            saved_run=saved_run,
            user=user,
            title=title,
            notes=notes,
            visibility=visibility,
        )

    def duplicate_published_run(
        self,
        published_run: PublishedRun,
        *,
        title: str,
        notes: str,
        visibility: PublishedRunVisibility,
    ):
        return published_run.duplicate(
            user=self.request.user,
            title=title,
            notes=notes,
            visibility=visibility,
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

    def render_author(
        self,
        user: AppUser,
        *,
        image_size: str = "30px",
        responsive: bool = True,
        show_as_link: bool = False,
        text_size: str | None = None,
    ):
        if not user or (not user.photo_url and not user.display_name):
            return

        responsive_image_size = (
            f"calc({image_size} * 0.67)" if responsive else image_size
        )

        # new class name so that different ones don't conflict
        class_name = f"author-image-{image_size}"
        if responsive:
            class_name += "-responsive"

        if show_as_link:
            linkto = st.link(
                to=self.app_url(
                    tab_name=MenuTabs.paths[MenuTabs.history],
                    query_params={"uid": user.uid},
                )
            )
        else:
            linkto = st.dummy()

        with linkto, st.div(className="d-flex align-items-center"):
            if user.photo_url:
                st.html(
                    f"""
                    <style>
                    .{class_name} {{
                        width: {responsive_image_size};
                        height: {responsive_image_size};
                        margin-right: 6px;
                        border-radius: 50%;
                        pointer-events: none;
                    }}

                    @media (min-width: 1024px) {{
                        .{class_name} {{
                            width: {image_size};
                            height: {image_size};
                        }}
                    }}
                    </style>
                """
                )
                st.image(user.photo_url, className=class_name)

            if user.display_name:
                name_style = {"fontSize": text_size} if text_size else {}
                with st.tag("span", style=name_style):
                    st.html(html.escape(user.display_name))

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
            col1.node.props["className"] += " d-flex flex-column justify-content-center"
            with col1:
                cost_note = self.get_cost_note() or ""
                if cost_note:
                    cost_note = f"({cost_note.strip()})"
                st.caption(
                    f"""
Run cost = <a href="{self.get_credits_click_url()}">{self.get_price_roundoff(st.session_state)} credits</a> {cost_note}
{self.additional_notes() or ""}
                    """,
                    unsafe_allow_html=True,
                )
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
                st.error(str(e))
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
        # only logged in users can report a run (but not examples/default runs)
        if not (self.request.user and run_id and uid):
            return

        reported = st.button(
            '<i class="fa-regular fa-flag"></i> Report', type="tertiary"
        )
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
        self.render_form_v2()
        with st.expander("⚙️ Settings"):
            self.render_settings()
            st.write("---")
        submitted = self.render_submit_button()
        with st.div(style={"textAlign": "right"}):
            st.caption(
                "_By submitting, you agree to Gooey.AI's [terms](https://gooey.ai/terms) & "
                "[privacy policy](https://gooey.ai/privacy)._"
            )
        return submitted

    @classmethod
    def get_run_state(cls, state: dict[str, typing.Any]) -> RecipeRunState:
        if state.get(StateKeys.run_status):
            return RecipeRunState.running
        elif state.get(StateKeys.error_msg):
            return RecipeRunState.failed
        elif state.get(StateKeys.run_time):
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

        run_state = self.get_run_state(st.session_state)
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

        if run_state != RecipeRunState.running:
            self._render_after_output()

    def _render_completed_output(self):
        pass

    def _render_failed_output(self):
        err_msg = st.session_state.get(StateKeys.error_msg)
        st.error(err_msg, unsafe_allow_html=True)

    def _render_running_output(self):
        run_status = st.session_state.get(StateKeys.run_status)
        html_spinner(run_status)
        self.render_extra_waiting_output()

    def render_extra_waiting_output(self):
        estimated_run_time = self.estimate_run_duration()
        if not estimated_run_time:
            return
        if created_at := st.session_state.get("created_at"):
            if isinstance(created_at, str):
                created_at = datetime.datetime.fromisoformat(created_at)
            with st.countdown_timer(
                end_time=created_at + datetime.timedelta(seconds=estimated_run_time),
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
            self.clean_query_params(example_id=None, run_id=run_id, uid=uid)
        )

    def should_submit_after_login(self) -> bool:
        return (
            st.get_query_params().get(SUBMIT_AFTER_LOGIN_Q)
            and self.request
            and self.request.user
            and not self.request.user.is_anonymous
        )

    def create_new_run(self, is_api_call: bool = False):
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
        published_run = self.get_current_published_run()
        try:
            parent_version = published_run and published_run.versions.latest()
        except PublishedRunVersion.DoesNotExist:
            parent_version = None

        self.run_doc_sr(
            run_id,
            uid,
            create=True,
            defaults=dict(
                parent=parent,
                parent_version=parent_version,
                is_api_call=is_api_call,
            ),
        ).set(self.state_to_doc(st.session_state))

        return None, run_id, uid

    def call_runner_task(self, example_id, run_id, uid, is_api_call=False):
        from celeryapp.tasks import gui_runner

        return gui_runner.delay(
            page_cls=self.__class__,
            user_id=self.request.user.id,
            run_id=run_id,
            uid=uid,
            state=st.session_state,
            channel=self.realtime_channel_name(run_id, uid),
            query_params=self.clean_query_params(
                example_id=example_id, run_id=run_id, uid=uid
            ),
            is_api_call=is_api_call,
        )

    def realtime_channel_name(self, run_id, uid):
        return f"gooey-outputs/{self.slug_versions[0]}/{uid}/{run_id}"

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
        self._render_report_button()

        if "seed" in self.RequestModel.schema_json():
            randomize = st.button(
                '<i class="fa-solid fa-recycle"></i> Regenerate', type="tertiary"
            )
            if randomize:
                st.session_state[StateKeys.pressed_randomize] = True
                st.experimental_rerun()

        render_output_caption()

    def state_to_doc(self, state: dict):
        ret = {
            field_name: deepcopy(state[field_name])
            for field_name in self.fields_to_save()
            if field_name in state
        }

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
        allow_hide = self.is_current_user_admin()

        def _render(pr: PublishedRun):
            self._render_example_preview(
                published_run=pr,
                allow_hide=allow_hide,
            )

        example_runs = PublishedRun.objects.filter(
            workflow=self.workflow,
            visibility=PublishedRunVisibility.PUBLIC,
            is_approved_example=True,
        ).exclude(published_run_id="")[:50]

        grid_layout(3, example_runs, _render, column_props=dict(className="mb-0 pb-0"))

    def _saved_tab(self):
        self.ensure_authentication()

        published_runs = PublishedRun.objects.filter(
            workflow=self.workflow,
            created_by=self.request.user,
        )[:50]
        if not published_runs:
            st.write("No published runs yet")
            return

        def _render(pr: PublishedRun):
            self._render_published_run_preview(published_run=pr)

        grid_layout(3, published_runs, _render)

    def ensure_authentication(self):
        if not self.request.user or self.request.user.is_anonymous:
            redirect_url = furl(
                "/login", query_params={"next": furl(self.request.url).set(origin=None)}
            )
            raise RedirectException(str(redirect_url))

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

        grid_layout(3, run_history, self._render_run_preview)

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

    def _render_run_preview(self, saved_run: SavedRun):
        published_run: PublishedRun | None = (
            saved_run.parent_version.published_run if saved_run.parent_version else None
        )
        is_latest_version = published_run and published_run.saved_run == saved_run
        tb = get_title_breadcrumbs(self, sr=saved_run, pr=published_run)

        with st.link(to=saved_run.get_app_url()):
            with st.div(className="mb-1", style={"font-size": "0.9rem"}):
                if is_latest_version:
                    st.html(
                        PublishedRunVisibility(
                            published_run.visibility
                        ).get_badge_html()
                    )

            st.write(f"#### {tb.h1_title}")

        updated_at = saved_run.updated_at
        if updated_at and isinstance(updated_at, datetime.datetime):
            js_dynamic_date(updated_at)

        if saved_run.run_status:
            html_spinner(saved_run.run_status)
        elif saved_run.error_msg:
            st.error(saved_run.error_msg, unsafe_allow_html=True)

        return self.render_example(saved_run.to_dict())

    def _render_published_run_preview(self, published_run: PublishedRun):
        tb = get_title_breadcrumbs(self, published_run.saved_run, published_run)

        with st.link(to=published_run.get_app_url()):
            with st.div(className="mb-1", style={"font-size": "0.9rem"}):
                st.html(
                    PublishedRunVisibility(published_run.visibility).get_badge_html()
                )

            st.write(f"#### {tb.h1_title}")

        with st.div(className="d-flex align-items-center justify-content-between"):
            with st.div():
                updated_at = published_run.updated_at
                if updated_at and isinstance(updated_at, datetime.datetime):
                    js_dynamic_date(updated_at)

            if published_run.visibility == PublishedRunVisibility.PUBLIC:
                run_icon = '<i class="fa-regular fa-person-running"></i>'
                run_count = format_number_with_suffix(published_run.get_run_count())
                st.caption(f"{run_icon} {run_count} runs", unsafe_allow_html=True)

        if published_run.notes:
            st.caption(published_run.notes)

        doc = published_run.saved_run.to_dict()
        self.render_example(doc)

    def _render_example_preview(
        self,
        *,
        published_run: PublishedRun,
        allow_hide: bool,
    ):
        tb = get_title_breadcrumbs(self, published_run.saved_run, published_run)

        with st.link(to=published_run.get_app_url()):
            with st.div(className="mb-1 text-truncate", style={"height": "1.5rem"}):
                if published_run.created_by and self.is_user_admin(
                    published_run.created_by
                ):
                    self.render_author(
                        published_run.created_by, image_size="20px", text_size="0.9rem"
                    )

            st.write(f"#### {tb.h1_title}")

        with st.div(className="d-flex align-items-center justify-content-between"):
            with st.div():
                updated_at = published_run.updated_at
                if updated_at and isinstance(updated_at, datetime.datetime):
                    js_dynamic_date(updated_at)

            run_icon = '<i class="fa-regular fa-person-running"></i>'
            run_count = format_number_with_suffix(published_run.get_run_count())
            st.caption(f"{run_icon} {run_count} runs", unsafe_allow_html=True)

        if published_run.notes:
            st.caption(published_run.notes)

        if allow_hide:
            self._example_hide_button(published_run=published_run)

        doc = published_run.saved_run.to_dict()
        self.render_example(doc)

    def _example_hide_button(self, published_run: PublishedRun):
        pressed_delete = st.button(
            "🙈️ Hide",
            key=f"delete_example_{published_run.published_run_id}",
            style={"color": "red"},
        )
        if not pressed_delete:
            return
        self.set_hidden(published_run=published_run, hidden=True)

    def set_hidden(self, *, published_run: PublishedRun, hidden: bool):
        with st.spinner("Hiding..."):
            published_run.is_approved_example = not hidden
            published_run.save()

        st.experimental_rerun()

    def render_example(self, state: dict):
        pass

    def render_steps(self):
        raise NotImplementedError

    @classmethod
    def preview_input(cls, state: dict) -> str | None:
        return (
            state.get("text_prompt")
            or state.get("input_prompt")
            or state.get("search_query")
            or state.get("title")
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
            f'📖 To learn more, take a look at our <a href="{api_docs_url}" target="_blank">complete API</a>',
            unsafe_allow_html=True,
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

    def get_cost_note(self) -> str | None:
        pass

    @classmethod
    def is_user_admin(cls, user: AppUser) -> bool:
        email = user.email
        return email and email in settings.ADMIN_EMAILS

    def is_current_user_admin(self) -> bool:
        if not self.request or not self.request.user:
            return False
        return self.is_user_admin(self.request.user)

    def is_current_user_paying(self) -> bool:
        return bool(self.request and self.request.user and self.request.user.is_paying)

    def is_current_user_owner(self) -> bool:
        return bool(
            self.request and self.request.user and self.run_user == self.request.user
        )


def render_output_caption():
    caption = ""

    run_time = st.session_state.get(StateKeys.run_time, 0)
    if run_time:
        caption += f'Generated in <span style="color: black;">{run_time :.2f}s</span>'

    if seed := st.session_state.get("seed"):
        caption += f' with seed <span style="color: black;">{seed}</span> '

    created_at = st.session_state.get(StateKeys.created_at, datetime.datetime.today())
    if created_at:
        if isinstance(created_at, str):
            created_at = datetime.datetime.fromisoformat(created_at)
        caption += " at&nbsp;"

    with st.div(className="d-flex"):
        st.caption(caption, unsafe_allow_html=True)
        js_dynamic_date(
            created_at,
            date_options={"month": "short", "day": "numeric", "year": "numeric"},
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


def force_redirect(url: str):
    # note: assumes sanitized URLs
    st.html(
        f"""
    <script>
    window.location = '{url}';
    </script>
    """
    )


class RedirectException(Exception):
    def __init__(self, url, status_code=302):
        self.url = url
        self.status_code = status_code


class QueryParamsRedirectException(RedirectException):
    def __init__(self, query_params: dict, status_code=303):
        query_params = {k: v for k, v in query_params.items() if v is not None}
        url = "?" + urllib.parse.urlencode(query_params)
        super().__init__(url, status_code)


class TitleValidationError(Exception):
    pass


def format_number_with_suffix(num: int) -> str:
    """
    Formats large number with a suffix.

    Ref: https://stackoverflow.com/a/45846841
    """
    num_float = float("{:.3g}".format(num))
    magnitude = 0
    while abs(num_float) >= 1000:
        magnitude += 1
        num_float /= 1000.0
    return "{}{}".format(
        "{:f}".format(num_float).rstrip("0").rstrip("."),
        ["", "K", "M", "B", "T"][magnitude],
    )
