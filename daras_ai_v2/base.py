import datetime
import html
import inspect
import json
import math
import typing
import uuid
from copy import deepcopy, copy
from enum import Enum
from itertools import pairwise
from random import Random
from time import sleep
from types import SimpleNamespace

import gooey_gui as gui
import sentry_sdk
from django.db.models import Sum
from django.utils import timezone
from django.utils.text import slugify
from fastapi import HTTPException
from firebase_admin import auth
from furl import furl
from pydantic import BaseModel, Field, ValidationError
from sentry_sdk.tracing import (
    TRANSACTION_SOURCE_ROUTE,
)
from starlette.requests import Request

from app_users.models import AppUser, AppUserTransaction
from bots.models import (
    SavedRun,
    PublishedRun,
    PublishedRunVersion,
    PublishedRunVisibility,
    Workflow,
    RetentionPolicy,
)
from daras_ai.image_input import truncate_text_words
from daras_ai.text_format import format_number_with_suffix
from daras_ai_v2 import settings, urls
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
from daras_ai_v2.exceptions import InsufficientCredits
from daras_ai_v2.fastapi_tricks import get_route_path
from daras_ai_v2.grid_layout_widget import grid_layout
from daras_ai_v2.html_spinner_widget import html_spinner
from daras_ai_v2.manage_api_keys_widget import manage_api_keys
from daras_ai_v2.meta_preview_url import meta_preview_url
from daras_ai_v2.prompt_vars import variables_input
from daras_ai_v2.query_params_util import (
    extract_query_params,
)
from daras_ai_v2.ratelimits import ensure_rate_limits, RateLimitExceeded
from daras_ai_v2.send_email import send_reported_run_email
from daras_ai_v2.user_date_widgets import (
    render_local_dt_attrs,
)
from functions.models import (
    RecipeFunction,
    FunctionTrigger,
)
from functions.recipe_functions import (
    functions_input,
    call_recipe_functions,
    is_functions_enabled,
    render_called_functions,
)
from payments.auto_recharge import (
    should_attempt_auto_recharge,
    run_auto_recharge_gracefully,
)
from routers.account import AccountTabs
from routers.root import RecipeTabs

DEFAULT_META_IMG = (
    # Small
    "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/ec2100aa-1f6e-11ef-ba0b-02420a000159/Main.jpg"
    # "https://storage.googleapis.com/dara-c1b52.appspot.com/meta_tag_default_img.jpg"
    # Big
    # "https://storage.googleapis.com/dara-c1b52.appspot.com/meta_tag_gif.gif"
)
MAX_SEED = 4294967294
gooey_rng = Random()


SUBMIT_AFTER_LOGIN_Q = "submitafterlogin"


class RecipeRunState(Enum):
    starting = "starting"
    running = "running"
    completed = "completed"
    failed = "failed"


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

    template_keys: typing.Iterable[str] = (
        "task_instructions",
        "query_instructions",
        "keyword_instructions",
        "input_prompt",
        "bot_script",
        "text_prompt",
        "search_query",
        "title",
    )

    class RequestModel(BaseModel):
        functions: list[RecipeFunction] | None = Field(
            title="🧩 Developer Tools and Functions",
        )
        variables: dict[str, typing.Any] = Field(
            None,
            title="⌥ Variables",
            description="Variables to be used as Jinja prompt templates and in functions as arguments",
        )

    ResponseModel: typing.Type[BaseModel]

    price = settings.CREDITS_TO_DEDUCT_PER_RUN

    def __init__(
        self,
        tab: RecipeTabs = "",
        request: Request | SimpleNamespace = None,
        run_user: AppUser = None,
    ):
        self.tab = tab
        self.request = request
        self.run_user = run_user

    @classmethod
    @property
    def endpoint(cls) -> str:
        return f"/v2/{cls.slug_versions[0]}"

    @classmethod
    def current_app_url(
        cls,
        tab: RecipeTabs = RecipeTabs.run,
        *,
        query_params: dict = None,
        path_params: dict = None,
    ) -> str:
        if query_params is None:
            query_params = {}
        example_id, run_id, uid = extract_query_params(gui.get_query_params())
        return cls.app_url(
            tab=tab,
            example_id=example_id,
            run_id=run_id,
            uid=uid,
            query_params=query_params,
            path_params=path_params,
        )

    @classmethod
    def app_url(
        cls,
        *,
        tab: RecipeTabs = None,
        example_id: str = None,
        run_id: str = None,
        uid: str = None,
        query_params: dict = None,
        path_params: dict = None,
    ) -> str:
        if not tab:
            tab = RecipeTabs.run
        if query_params is None:
            query_params = {}

        if run_id and uid:
            query_params |= dict(run_id=run_id, uid=uid)
        q_example_id = query_params.pop("example_id", None)

        # old urls had example_id as a query param
        example_id = example_id or q_example_id
        run_slug = None
        if example_id:
            try:
                pr = cls.get_published_run(published_run_id=example_id)
            except PublishedRun.DoesNotExist:
                pr = None
            if pr and pr.title:
                run_slug = slugify(pr.title)

        return str(
            furl(settings.APP_BASE_URL, query_params=query_params)
            / tab.url_path(
                page_slug=cls.slug_versions[-1],
                run_slug=run_slug,
                example_id=example_id,
                **(path_params or {}),
            )
        )

    @classmethod
    def current_api_url(cls) -> furl | None:
        pr = cls.get_current_published_run()
        return cls.api_url(example_id=pr and pr.published_run_id)

    @classmethod
    def api_url(
        cls,
        example_id: str = None,
        run_id: str = None,
        uid: str = None,
        query_params: dict = None,
    ) -> furl:
        query_params = query_params or {}
        if run_id and uid:
            query_params = dict(run_id=run_id, uid=uid)
        elif example_id:
            query_params = dict(example_id=example_id)
        return furl(settings.API_BASE_URL, query_params=query_params) / cls.endpoint

    @classmethod
    def clean_query_params(cls, *, example_id, run_id, uid) -> dict:
        query_params = {}
        if run_id and uid:
            query_params |= dict(run_id=run_id, uid=uid)
        if example_id:
            query_params |= dict(example_id=example_id)
        return query_params

    def get_dynamic_meta_title(self) -> str | None:
        return None

    def setup_sentry(self):
        with sentry_sdk.configure_scope() as scope:
            scope.set_transaction_name(
                "/" + self.slug_versions[0], source=TRANSACTION_SOURCE_ROUTE
            )
            scope.add_event_processor(self.sentry_event_set_request)
            scope.add_event_processor(self.sentry_event_set_user)

    def sentry_event_set_request(self, event, hint):
        request = event.setdefault("request", {})
        request.setdefault("method", "POST")
        request["data"] = gui.session_state
        if url := request.get("url"):
            f = furl(url)
            request["url"] = str(
                furl(settings.APP_BASE_URL, path=f.pathstr, query=f.querystr).url
            )
        else:
            request["url"] = self.app_url(
                tab=self.tab, query_params=gui.get_query_params()
            )
        return event

    def sentry_event_set_user(self, event, hint):
        if user := self.request and self.request.user:
            event["user"] = {
                "id": user.id,
                "name": user.display_name,
                "email": user.email,
                "data": {
                    field: getattr(user, field)
                    for field in [
                        "uid",
                        "phone_number",
                        "photo_url",
                        "balance",
                        "is_paying",
                        "is_anonymous",
                        "is_disabled",
                        "disable_safety_checker",
                        "disable_rate_limits",
                        "created_at",
                    ]
                },
            }
        return event

    def refresh_state(self):
        _, run_id, uid = extract_query_params(gui.get_query_params())
        channel = self.realtime_channel_name(run_id, uid)
        output = gui.realtime_pull([channel])[0]
        if output:
            gui.session_state.update(output)

    def render(self):
        self.setup_sentry()

        if self.get_run_state(gui.session_state) == RecipeRunState.running:
            self.refresh_state()
        else:
            gui.realtime_clear_subs()

        self._user_disabled_check()
        self._check_if_flagged()

        if gui.session_state.get("show_report_workflow"):
            self.render_report_form()
            return

        self._render_header()
        gui.newline()

        with gui.nav_tabs():
            for tab in self.get_tabs():
                url = self.current_app_url(tab)
                with gui.nav_item(url, active=tab == self.tab):
                    gui.html(tab.title)
        with gui.nav_tab_content():
            self.render_selected_tab()

    def _render_header(self):
        current_run = self.get_current_sr()
        published_run = self.get_current_published_run()
        is_example = published_run and published_run.saved_run == current_run
        is_root_example = is_example and published_run.is_root()
        tbreadcrumbs = get_title_breadcrumbs(
            self, current_run, published_run, tab=self.tab
        )

        with gui.div(className="d-flex justify-content-between mt-4"):
            with gui.div(className="d-lg-flex d-block align-items-center"):
                if not tbreadcrumbs.has_breadcrumbs() and not self.run_user:
                    self._render_title(tbreadcrumbs.h1_title)

                if tbreadcrumbs:
                    with gui.tag("div", className="me-3 mb-1 mb-lg-0 py-2 py-lg-0"):
                        render_breadcrumbs(
                            tbreadcrumbs,
                            is_api_call=(
                                current_run.is_api_call and self.tab == RecipeTabs.run
                            ),
                        )

                if is_example:
                    assert published_run
                    author = published_run.created_by
                else:
                    author = self.run_user or current_run.get_creator()
                if not is_root_example:
                    self.render_author(author)

            with gui.div(className="d-flex align-items-center"):
                can_user_edit_run = self.can_user_edit_run(current_run, published_run)
                has_unpublished_changes = (
                    published_run
                    and published_run.saved_run != current_run
                    and self.request
                    and self.request.user
                    and published_run.created_by == self.request.user
                )

                if can_user_edit_run and has_unpublished_changes:
                    self._render_unpublished_changes_indicator()

                with gui.div(className="d-flex align-items-start right-action-icons"):
                    gui.html(
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

        if tbreadcrumbs.has_breadcrumbs() or self.run_user:
            # only render title here if the above row was not empty
            self._render_title(tbreadcrumbs.h1_title)

        if self.tab != RecipeTabs.run:
            return
        if published_run and published_run.notes:
            gui.write(published_run.notes, line_clamp=2)
        elif is_root_example and self.tab != RecipeTabs.integrations:
            gui.write(self.preview_description(current_run.to_dict()), line_clamp=2)

    def can_user_edit_run(
        self,
        current_run: SavedRun,
        published_run: PublishedRun | None,
    ) -> bool:
        return (
            self.is_current_user_admin()
            or bool(
                self.request
                and self.request.user
                and current_run.uid == self.request.user.uid
            )
            or bool(
                published_run
                and published_run.saved_run == current_run
                and self.can_user_edit_published_run(published_run)
            )
        )

    def can_user_edit_published_run(
        self, published_run: PublishedRun | None = None
    ) -> bool:
        published_run = published_run or self.get_current_published_run()
        return self.is_current_user_admin() or bool(
            published_run
            and self.request
            and self.request.user
            and published_run.created_by == self.request.user
        )

    def _render_title(self, title: str):
        gui.write(f"# {title}")

    def _render_unpublished_changes_indicator(self):
        with gui.div(
            className="d-none d-lg-flex h-100 align-items-center text-muted ms-2"
        ):
            with gui.tag("span", className="d-inline-block"):
                gui.html("Unpublished changes")

    def _render_social_buttons(self, show_button_text: bool = False):
        button_text = (
            '<span class="d-none d-lg-inline"> Copy Link</span>'
            if show_button_text
            else ""
        )

        copy_to_clipboard_button(
            f'<i class="fa-regular fa-link"></i>{button_text}',
            value=self.current_app_url(self.tab),
            type="secondary",
            className="mb-0 ms-lg-2",
        )

    def _render_published_run_buttons(
        self,
        *,
        current_run: SavedRun,
        published_run: PublishedRun,
        redirect_to: str | None = None,
    ):
        is_update_mode = (
            self.is_current_user_admin()
            or published_run.created_by == self.request.user
        )

        with gui.div(className="d-flex justify-content-end"):
            gui.html(
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

            pressed_options = is_update_mode and gui.button(
                '<i class="fa-regular fa-ellipsis"></i>',
                className="mb-0 ms-lg-2",
                type="tertiary",
            )
            options_modal = gui.Modal("Options", key="published-run-options-modal")
            if pressed_options:
                options_modal.open()
            if options_modal.is_open():
                with options_modal.container(style={"minWidth": "min(300px, 100vw)"}):
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
            pressed_save = gui.button(
                f'{save_icon} <span class="d-none d-lg-inline">{save_text}</span>',
                className="mb-0 ms-lg-2 px-lg-4",
                type="primary",
            )
            publish_modal = gui.Modal("Publish to", key="publish-modal")
            if pressed_save:
                publish_modal.open()
            if publish_modal.is_open():
                with publish_modal.container(style={"minWidth": "min(500px, 100vw)"}):
                    self._render_publish_modal(
                        current_run=current_run,
                        published_run=published_run,
                        modal=publish_modal,
                        is_update_mode=is_update_mode,
                        redirect_to=redirect_to,
                    )

    def _render_publish_modal(
        self,
        *,
        current_run: SavedRun,
        published_run: PublishedRun,
        modal: gui.Modal,
        is_update_mode: bool = False,
        redirect_to: str | None = None,
    ):
        if published_run.is_root() and self.is_current_user_admin():
            with gui.div(className="text-danger"):
                gui.write(
                    "###### You're about to update the root workflow as an admin. "
                )
            gui.html(
                'If you want to create a new example, press <i class="fa-regular fa-ellipsis"></i> and "Duplicate" instead.'
            )
            published_run_visibility = PublishedRunVisibility.PUBLIC
        else:
            with gui.div(className="visibility-radio"):
                options = {
                    str(enum.value): enum.help_text() for enum in PublishedRunVisibility
                }
                if self.request.user and self.request.user.handle:
                    profile_url = self.request.user.handle.get_app_url()
                    pretty_profile_url = urls.remove_scheme(profile_url).rstrip("/")
                    options[
                        str(PublishedRunVisibility.PUBLIC.value)
                    ] += f' <span class="text-muted">on [{pretty_profile_url}]({profile_url})</span>'
                elif self.request.user and not self.request.user.is_anonymous:
                    edit_profile_url = AccountTabs.profile.url_path
                    options[
                        str(PublishedRunVisibility.PUBLIC.value)
                    ] += f' <span class="text-muted">on my [profile page]({edit_profile_url})</span>'

                published_run_visibility = PublishedRunVisibility(
                    int(
                        gui.radio(
                            "",
                            options=options,
                            format_func=options.__getitem__,
                            value=str(published_run.visibility),
                        )
                    )
                )
                gui.radio(
                    "",
                    options=[
                        '<span class="text-muted">Anyone at my org (coming soon)</span>'
                    ],
                    disabled=True,
                    checked_by_default=False,
                )

        with gui.div(className="mt-4"):
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
            published_run_title = gui.text_input(
                "##### Title",
                key="published_run_title",
                value=title,
            )
            published_run_notes = gui.text_area(
                "##### Notes",
                key="published_run_notes",
                value=(
                    published_run.notes
                    or self.preview_description(gui.session_state)
                    or ""
                ),
            )

        with gui.div(className="mt-4 d-flex justify-content-center"):
            pressed_save = gui.button(
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
                gui.error(str(e))
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
                gui.error("No changes to publish", icon="⚠️")
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
        raise gui.RedirectException(redirect_to or published_run.get_app_url())

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
        modal: gui.Modal,
    ):
        is_latest_version = published_run.saved_run == current_run

        with gui.div(className="mt-4"):
            duplicate_button = None
            save_as_new_button = None
            duplicate_icon = save_as_new_icon = '<i class="fa-regular fa-copy"></i>'
            if is_latest_version:
                duplicate_button = gui.button(
                    f"{duplicate_icon} Duplicate", className="w-100"
                )
            else:
                save_as_new_button = gui.button(
                    f"{save_as_new_icon} Save as New", className="w-100"
                )
            delete_button = not published_run.is_root() and gui.button(
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
            raise gui.RedirectException(
                self.app_url(example_id=duplicate_pr.published_run_id)
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
            raise gui.RedirectException(
                self.app_url(example_id=new_pr.published_run_id)
            )

        with gui.div(className="mt-4"):
            gui.write("#### Version History", className="mb-4")
            self._render_version_history()

        confirm_delete_modal = gui.Modal("Confirm Delete", key="confirm-delete-modal")
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
        modal: gui.Modal,
    ):
        gui.write(
            "Are you sure you want to delete this published run? "
            f"_({published_run.title})_"
        )
        gui.caption("This will also delete all the associated versions.")
        with gui.div(className="d-flex"):
            confirm_button = gui.button(
                '<span class="text-danger">Confirm</span>',
                type="secondary",
                className="w-100",
            )
            cancel_button = gui.button(
                "Cancel",
                type="secondary",
                className="w-100",
            )

        if confirm_button:
            published_run.delete()
            raise gui.RedirectException(self.app_url())

        if cancel_button:
            modal.close()

    def _render_admin_options(self, current_run: SavedRun, published_run: PublishedRun):
        if (
            not self.is_current_user_admin()
            or published_run.is_root()
            or published_run.saved_run != current_run
        ):
            return

        with gui.expander("🛠️ Admin Options"):
            gui.write(
                f"This will hide/show this workflow from {self.app_url(tab=RecipeTabs.examples)}  \n"
                f"(Given that you have set public visibility above)"
            )
            if gui.session_state.get("--toggle-approve-example"):
                published_run.is_approved_example = (
                    not published_run.is_approved_example
                )
                published_run.save(update_fields=["is_approved_example"])
            if published_run.is_approved_example:
                btn_text = "🙈 Hide from Examples"
            else:
                btn_text = "✅ Approve as Example"
            gui.button(btn_text, key="--toggle-approve-example")

            if published_run.is_approved_example:
                example_priority = gui.number_input(
                    "Example Priority (Between 1 to 100 - Default is 1)",
                    min_value=1,
                    max_value=100,
                    value=published_run.example_priority,
                )
                if example_priority != published_run.example_priority:
                    if gui.button("Save Priority"):
                        published_run.example_priority = example_priority
                        published_run.save(update_fields=["example_priority"])
                        gui.rerun()

            gui.write("---")

            if gui.checkbox("⭐️ Save as Root Workflow"):
                gui.write(
                    f"Are you Sure?  \n"
                    f"This will overwrite the contents of {self.app_url()}",
                    className="text-danger",
                )
                if gui.button("👌 Yes, Update the Root Workflow"):
                    root_run = self.get_root_published_run()
                    root_run.add_version(
                        user=self.request.user,
                        title=published_run.title,
                        notes=published_run.notes,
                        saved_run=published_run.saved_run,
                        visibility=PublishedRunVisibility.PUBLIC,
                    )
                    raise gui.RedirectException(self.app_url())

    @classmethod
    def get_recipe_title(cls) -> str:
        return cls.get_root_published_run().title or cls.title or cls.workflow.label

    def get_explore_image(self) -> str:
        meta = self.workflow.get_or_create_metadata()
        img = meta.default_image or self.explore_image or ""
        fallback_img = self.fallback_preivew_image()
        return meta_preview_url(img, fallback_img)

    def _user_disabled_check(self):
        if self.run_user and self.run_user.is_disabled:
            msg = (
                "This Gooey.AI account has been disabled for violating our [Terms of Service](/terms). "
                "Contact us at support@gooey.ai if you think this is a mistake."
            )
            gui.error(msg, icon="😵")
            gui.stop()

    def get_tabs(self):
        tabs = [RecipeTabs.run, RecipeTabs.examples, RecipeTabs.run_as_api]
        if self.request.user:
            tabs.extend([RecipeTabs.history])
        if self.request.user and not self.request.user.is_anonymous:
            tabs.extend([RecipeTabs.saved])
        return tabs

    def render_selected_tab(self):
        match self.tab:
            case RecipeTabs.run:
                if self.get_current_sr().retention_policy == RetentionPolicy.delete:
                    self.render_deleted_output()
                    return

                input_col, output_col = gui.columns([3, 2], gap="medium")
                with input_col:
                    submitted = self._render_input_col()
                with output_col:
                    self._render_output_col(submitted=submitted)

                self._render_step_row()

                col1, col2 = gui.columns(2)
                with col1:
                    self._render_help()

                self.render_related_workflows()

            case RecipeTabs.examples:
                self._examples_tab()

            case RecipeTabs.history:
                self._history_tab()

            case RecipeTabs.run_as_api:
                self.run_as_api_tab()

            case RecipeTabs.saved:
                self._saved_tab()

    def _render_version_history(self):
        published_run = self.get_current_published_run()

        if published_run:
            versions = published_run.versions.all()
            first_version = versions[0]
            for version, older_version in pairwise(versions):
                first_version = older_version
                self._render_version_row(version, older_version)
            self._render_version_row(first_version, None)

    def _render_version_row(
        self,
        version: PublishedRunVersion,
        older_version: PublishedRunVersion | None,
    ):
        gui.html(
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
        with gui.link(to=url, className="text-decoration-none"):
            with gui.div(
                className="d-flex mb-4 disable-p-margin",
                style={"minWidth": "min(100vw, 500px)"},
            ):
                col1 = gui.div(className="me-4")
                col2 = gui.div()
        with col1:
            with gui.div(className="fs-5 mt-1"):
                gui.html('<i class="fa-regular fa-clock"></i>')
        with col2:
            is_first_version = not older_version
            with gui.div(className="fs-5 d-flex align-items-center"):
                with gui.tag("span"):
                    gui.html(
                        "Loading...",
                        **render_local_dt_attrs(
                            version.created_at,
                            date_options={"month": "short", "day": "numeric"},
                        ),
                    )
                if is_first_version:
                    with gui.tag("span", className="badge bg-secondary px-3 ms-2"):
                        gui.write("FIRST VERSION")
            with gui.div(className="text-muted"):
                if older_version and older_version.title != version.title:
                    gui.write(f"Renamed: {version.title}")
                elif not older_version:
                    gui.write(version.title)
            with gui.div(className="mt-1", style={"fontSize": "0.85rem"}):
                self.render_author(
                    version.changed_by, image_size="18px", responsive=False
                )

    def render_related_workflows(self):
        page_clses = self.related_workflows()
        if not page_clses:
            return

        with gui.link(to="/explore/"):
            gui.html("<h2>Related Workflows</h2>")

        def _render(page_cls: typing.Type[BasePage]):
            page = page_cls()
            root_run = page.get_root_published_run()
            state = root_run.saved_run.to_dict()
            preview_image = page.get_explore_image()

            with gui.link(to=page.app_url(), className="text-decoration-none"):
                gui.html(
                    # language=html
                    f"""
<div class="w-100 mb-2" style="height:150px; background-image: url({preview_image}); background-size:cover; background-position-x:center; background-position-y:30%; background-repeat:no-repeat;"></div>
                    """
                )
                gui.markdown(f"###### {root_run.title or page.title}")
                gui.caption(
                    truncate_text_words(
                        root_run.notes or page.preview_description(state),
                        maxlen=210,
                    )
                )

        grid_layout(4, page_clses, _render)

    def related_workflows(self) -> list:
        return []

    def render_report_form(self):
        with gui.form("report_form"):
            gui.write(
                """
                ## Report a Workflow
                Generative AI is powerful, but these technologies are also unmoderated. Sometimes the output of workflows can be inappropriate or incorrect. It might be broken or buggy. It might cause copyright issues. It might be inappropriate content.
                Whatever the reason, please use this form to tell us when something is wrong with the output of a workflow you've run or seen on our site.
                We'll investigate the reported workflow and its output and take appropriate action. We may flag this workflow or its author so they are aware too.
                """
            )

            gui.write("#### Your Report")

            gui.text_input(
                "Workflow",
                disabled=True,
                value=self.title,
            )

            current_url = self.current_app_url()
            gui.text_input(
                "Run URL",
                disabled=True,
                value=current_url,
            )

            gui.write("Output")
            self.render_output()

            inappropriate_radio_text = "Inappropriate content"
            report_type = gui.radio(
                "Report Type", ("Buggy Output", inappropriate_radio_text, "Other")
            )
            reason_for_report = gui.text_area(
                "Reason for report",
                placeholder="Tell us why you are reporting this workflow e.g. an error, inappropriate content, very poor output, etc. Please let know what you expected as well. ",
            )

            col1, col2 = gui.columns(2)
            with col1:
                submitted = gui.form_submit_button("✅ Submit Report")
            with col2:
                cancelled = gui.form_submit_button("❌ Cancel")

        if cancelled:
            gui.session_state["show_report_workflow"] = False
            gui.rerun()

        if submitted:
            if not reason_for_report:
                gui.error("Reason for report cannot be empty")
                return

            example_id, run_id, uid = extract_query_params(gui.get_query_params())

            send_reported_run_email(
                user=self.request.user,
                run_uid=uid,
                url=self.current_app_url(),
                recipe_name=self.title,
                report_type=report_type,
                reason_for_report=reason_for_report,
                error_msg=gui.session_state.get(StateKeys.error_msg),
            )

            if report_type == inappropriate_radio_text:
                self.update_flag_for_run(run_id=run_id, uid=uid, is_flagged=True)

            # gui.success("Reported.")
            gui.session_state["show_report_workflow"] = False
            gui.rerun()

    def _check_if_flagged(self):
        if not gui.session_state.get("is_flagged"):
            return

        gui.error("### This Content has been Flagged")

        if self.is_current_user_admin():
            unflag_pressed = gui.button("UnFlag")
            if not unflag_pressed:
                return
            with gui.spinner("Removing flag..."):
                example_id, run_id, uid = extract_query_params(gui.get_query_params())
                if run_id and uid:
                    self.update_flag_for_run(run_id=run_id, uid=uid, is_flagged=False)
            gui.success("Removed flag.", icon="✅")
            sleep(2)
            gui.rerun()
        else:
            gui.write(
                "Our support team is reviewing this run. Please come back after some time."
            )
            # Return and Don't render the run any further
            gui.stop()

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
        example_id, run_id, uid = extract_query_params(gui.get_query_params())
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
    def get_published_run(cls, *, published_run_id: str):
        return PublishedRun.objects.get(
            workflow=cls.workflow,
            published_run_id=published_run_id,
        )

    @classmethod
    def get_current_sr(cls) -> SavedRun:
        return cls.get_sr_from_query_params_dict(gui.get_query_params())

    @classmethod
    def get_sr_from_query_params_dict(cls, query_params) -> SavedRun:
        example_id, run_id, uid = extract_query_params(query_params)
        return cls.get_sr_from_query_params(example_id, run_id, uid)

    @classmethod
    def get_sr_from_query_params(
        cls, example_id: str | None, run_id: str | None, uid: str | None
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
    def recipe_doc_sr(cls, create: bool = True) -> SavedRun:
        if create:
            return cls.get_root_published_run().saved_run
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
    def get_root_published_run(cls) -> PublishedRun:
        return PublishedRun.objects.get_or_create_with_version(
            workflow=cls.workflow,
            published_run_id="",
            saved_run=SavedRun.objects.get_or_create(
                example_id="",
                workflow=cls.workflow,
                defaults=dict(state=cls.load_state_defaults({})),
            )[0],
            user=None,
            title=cls.title,
            notes=cls().preview_description(state=cls.sane_defaults),
            visibility=PublishedRunVisibility.PUBLIC,
        )[0]

    @classmethod
    def create_published_run(
        cls,
        *,
        published_run_id: str,
        saved_run: SavedRun,
        user: AppUser | None,
        title: str,
        notes: str,
        visibility: PublishedRunVisibility,
    ):
        return PublishedRun.objects.create_with_version(
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
        self.render_example(gui.session_state)

    def render_form_v2(self):
        pass

    def validate_form_v2(self):
        pass

    @staticmethod
    def render_author(
        user: AppUser,
        *,
        image_size: str = "30px",
        responsive: bool = True,
        show_as_link: bool = True,
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

        if show_as_link and user and user.handle:
            linkto = gui.link(to=user.handle.get_app_url())
        else:
            linkto = gui.dummy()

        with linkto, gui.div(className="d-flex align-items-center"):
            if user.photo_url:
                gui.html(
                    f"""
                    <style>
                    .{class_name} {{
                        width: {responsive_image_size};
                        height: {responsive_image_size};
                        margin-right: 6px;
                        border-radius: 50%;
                        object-fit: cover;
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
                gui.image(user.photo_url, className=class_name)

            if user.display_name:
                name_style = {"fontSize": text_size} if text_size else {}
                with gui.tag("span", style=name_style):
                    gui.html(html.escape(user.display_name))

    def get_credits_click_url(self):
        if self.request.user and self.request.user.is_anonymous:
            return "/pricing/"
        else:
            return "/account/"

    def get_submit_container_props(self):
        return dict(
            className="position-sticky bottom-0 bg-white", style=dict(zIndex=100)
        )

    def render_submit_button(self, key="--submit-1"):
        with gui.div(**self.get_submit_container_props()):
            gui.write("---")
            col1, col2 = gui.columns([2, 1], responsive=False)
            col2.node.props[
                "className"
            ] += " d-flex justify-content-end align-items-center"
            col1.node.props["className"] += " d-flex flex-column justify-content-center"
            with col1:
                self.render_run_cost()
            with col2:
                submitted = gui.button(
                    "🏃 Submit",
                    key=key,
                    type="primary",
                    # disabled=bool(gui.session_state.get(StateKeys.run_status)),
                )
            if not submitted:
                return False
            try:
                self.validate_form_v2()
            except AssertionError as e:
                gui.error(str(e))
                return False
            else:
                return True

    def render_run_cost(self):
        url = self.get_credits_click_url()
        run_cost = self.get_price_roundoff(gui.session_state)
        ret = f'Run cost = <a href="{url}">{run_cost} credits</a>'

        cost_note = self.get_cost_note()
        if cost_note:
            ret += f" ({cost_note.strip()})"

        additional_notes = self.additional_notes()
        if additional_notes:
            ret += f" \n{additional_notes}"

        gui.caption(ret, line_clamp=1, unsafe_allow_html=True)

    def _render_step_row(self):
        key = "details-expander"
        with gui.expander("**ℹ️ Details**", key=key):
            if not gui.session_state.get(key):
                return
            col1, col2 = gui.columns([1, 2])
            with col1:
                self.render_description()
            with col2:
                placeholder = gui.div()
                render_called_functions(
                    saved_run=self.get_current_sr(), trigger=FunctionTrigger.pre
                )
                try:
                    self.render_steps()
                except NotImplementedError:
                    pass
                else:
                    with placeholder:
                        gui.write("##### 👣 Steps")
                render_called_functions(
                    saved_run=self.get_current_sr(), trigger=FunctionTrigger.post
                )

    def _render_help(self):
        placeholder = gui.div()
        try:
            self.render_usage_guide()
        except NotImplementedError:
            pass
        else:
            with placeholder:
                gui.write(
                    """
                    ## How to Use This Recipe
                    """
                )

        key = "discord-expander"
        with gui.expander(
            f"**🙋🏽‍♀️ Need more help? [Join our Discord]({settings.DISCORD_INVITE_URL})**",
            key=key,
        ):
            if not gui.session_state.get(key):
                return
            gui.markdown(
                """
                <div style="position: relative; padding-bottom: 56.25%; height: 500px; max-width: 500px;">
                <iframe src="https://e.widgetbot.io/channels/643360566970155029/1046049067337273444" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;"></iframe>
                </div>
                """,
                unsafe_allow_html=True,
            )

    def render_usage_guide(self):
        raise NotImplementedError

    def main(self, sr: SavedRun, state: dict) -> typing.Iterator[str | None]:
        yield from self.ensure_credits_and_auto_recharge(sr, state)

        yield from call_recipe_functions(
            saved_run=sr,
            current_user=self.request.user,
            request_model=self.RequestModel,
            response_model=self.ResponseModel,
            state=state,
            trigger=FunctionTrigger.pre,
        )

        yield from self.run(state)

        yield from call_recipe_functions(
            saved_run=sr,
            current_user=self.request.user,
            request_model=self.RequestModel,
            response_model=self.ResponseModel,
            state=state,
            trigger=FunctionTrigger.post,
        )

    def run(self, state: dict) -> typing.Iterator[str | None]:
        # initialize request and response
        request = self.RequestModel.parse_obj(state)
        response = self.ResponseModel.construct()

        # run the recipe
        try:
            for val in self.run_v2(request, response):
                state.update(response.dict(exclude_unset=True))
                yield val
        finally:
            state.update(response.dict(exclude_unset=True))

        # validate the response if successful
        self.ResponseModel.validate(response)

    def run_v2(
        self, request: RequestModel, response: BaseModel
    ) -> typing.Iterator[str | None]:
        raise NotImplementedError

    def _render_report_button(self):
        example_id, run_id, uid = extract_query_params(gui.get_query_params())
        # only logged in users can report a run (but not examples/default runs)
        if not (self.request.user and run_id and uid):
            return

        reported = gui.button(
            '<i class="fa-regular fa-flag"></i> Report', type="tertiary"
        )
        if not reported:
            return

        gui.session_state["show_report_workflow"] = reported
        gui.rerun()

    def update_flag_for_run(self, run_id: str, uid: str, is_flagged: bool):
        ref = self.run_doc_sr(uid=uid, run_id=run_id)
        ref.is_flagged = is_flagged
        ref.save(update_fields=["is_flagged"])
        gui.session_state["is_flagged"] = is_flagged

    # Functions in every recipe feels like overkill for now, hide it in settings
    functions_in_settings = True
    show_settings = True

    def _render_input_col(self):
        self.render_form_v2()
        placeholder = gui.div()

        if self.show_settings:
            with gui.expander("⚙️ Settings"):
                self.render_settings()
                if self.functions_in_settings:
                    functions_input(self.request.user, is_in_settings=True)

        with placeholder:
            self.render_variables()

        submitted = self.render_submit_button()
        with gui.div(style={"textAlign": "right"}):
            gui.caption(
                "_By submitting, you agree to Gooey.AI's [terms](https://gooey.ai/terms) & "
                "[privacy policy](https://gooey.ai/privacy)._"
            )
        return submitted

    def render_variables(self):
        if not self.functions_in_settings:
            functions_input(self.request.user)
        variables_input(
            template_keys=self.template_keys, allow_add=is_functions_enabled()
        )

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
            return RecipeRunState.starting

    def render_deleted_output(self):
        col1, *_ = gui.columns(2)
        with col1:
            gui.error(
                "This data has been deleted as per the retention policy.",
                icon="🗑️",
                color="rgba(255, 200, 100, 0.5)",
            )
            gui.newline()
            self._render_output_col(is_deleted=True)
            gui.newline()
            self.render_run_cost()

    def _render_output_col(self, *, submitted: bool = False, is_deleted: bool = False):
        assert inspect.isgeneratorfunction(self.run)

        if gui.session_state.get(StateKeys.pressed_randomize):
            gui.session_state["seed"] = int(gooey_rng.randrange(MAX_SEED))
            gui.session_state.pop(StateKeys.pressed_randomize, None)
            submitted = True

        if submitted or self.should_submit_after_login():
            self.on_submit()

        run_state = self.get_run_state(gui.session_state)
        match run_state:
            case RecipeRunState.completed:
                self._render_completed_output()
            case RecipeRunState.failed:
                self._render_failed_output()
            case RecipeRunState.running:
                self._render_running_output()
            case RecipeRunState.starting:
                pass

        # render outputs
        if not is_deleted:
            self.render_output()

        if run_state != RecipeRunState.running:
            if not is_deleted:
                self._render_after_output()
            render_output_caption()

    def _render_completed_output(self):
        pass

    def _render_failed_output(self):
        err_msg = gui.session_state.get(StateKeys.error_msg)
        gui.error(err_msg, unsafe_allow_html=True)

    def _render_running_output(self):
        run_status = gui.session_state.get(StateKeys.run_status)
        html_spinner(run_status)
        self.render_extra_waiting_output()

    def render_extra_waiting_output(self):
        created_at = gui.session_state.get("created_at")
        if not created_at:
            return

        if isinstance(created_at, str):
            created_at = datetime.datetime.fromisoformat(created_at)
        started_at_text(created_at)

        estimated_run_time = self.estimate_run_duration()
        if not estimated_run_time:
            return
        with gui.countdown_timer(
            end_time=created_at + datetime.timedelta(seconds=estimated_run_time),
            delay_text="Sorry for the wait. Your run is taking longer than we expected.",
        ):
            if self.is_current_user_owner() and self.request.user.email:
                gui.write(
                    f"""We'll email **{self.request.user.email}** when your workflow is done."""
                )
            gui.write(
                f"""In the meantime, check out [🚀 Examples]({self.current_app_url(RecipeTabs.examples)})
                  for inspiration."""
            )

    def estimate_run_duration(self) -> int | None:
        pass

    def on_submit(self):
        try:
            sr = self.create_new_run(enable_rate_limits=True)
        except ValidationError as e:
            gui.session_state[StateKeys.run_status] = None
            gui.session_state[StateKeys.error_msg] = str(e)
            return
        except RateLimitExceeded as e:
            gui.session_state[StateKeys.run_status] = None
            gui.session_state[StateKeys.error_msg] = e.detail.get("error", "")
            return

        self.call_runner_task(sr)

        raise gui.RedirectException(self.app_url(run_id=sr.run_id, uid=sr.uid))

    def should_submit_after_login(self) -> bool:
        return (
            gui.get_query_params().get(SUBMIT_AFTER_LOGIN_Q)
            and self.request
            and self.request.user
            and not self.request.user.is_anonymous
        )

    def create_new_run(
        self, *, enable_rate_limits: bool = False, **defaults
    ) -> SavedRun:
        gui.session_state[StateKeys.run_status] = "Starting..."
        gui.session_state.pop(StateKeys.error_msg, None)
        gui.session_state.pop(StateKeys.run_time, None)
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

        if enable_rate_limits:
            ensure_rate_limits(self.workflow, self.request.user)

        run_id = get_random_doc_id()

        parent_example_id, parent_run_id, parent_uid = extract_query_params(
            gui.get_query_params()
        )
        parent = self.get_sr_from_query_params(
            parent_example_id, parent_run_id, parent_uid
        )
        published_run = self.get_current_published_run()
        try:
            parent_version = published_run and published_run.versions.latest()
        except PublishedRunVersion.DoesNotExist:
            parent_version = None

        sr = self.run_doc_sr(
            run_id,
            uid,
            create=True,
            defaults=dict(parent=parent, parent_version=parent_version) | defaults,
        )

        # ensure the request is validated
        state = gui.session_state | json.loads(
            self.RequestModel.parse_obj(gui.session_state).json(exclude_unset=True)
        )
        self.dump_state_to_sr(state, sr)

        return sr

    def dump_state_to_sr(self, state: dict, sr: SavedRun):
        sr.set(
            {
                field_name: deepcopy(state[field_name])
                for field_name in self.fields_to_save()
                if field_name in state
            }
        )

    def call_runner_task(self, sr: SavedRun):
        from celeryapp.tasks import runner_task, post_runner_tasks

        chain = (
            runner_task.s(
                page_cls=self.__class__,
                user_id=self.request.user.id,
                run_id=sr.run_id,
                uid=sr.uid,
                channel=self.realtime_channel_name(sr.run_id, sr.uid),
                unsaved_state=self._unsaved_state(),
            )
            | post_runner_tasks.s()
        )
        return chain.apply_async()

    @classmethod
    def realtime_channel_name(cls, run_id, uid):
        return f"gooey-outputs/{cls.slug_versions[0]}/{uid}/{run_id}"

    def generate_credit_error_message(self, run_id, uid) -> str:
        account_url = furl(settings.APP_BASE_URL) / "account/"
        if self.request.user.is_anonymous:
            account_url.query.params["next"] = self.app_url(
                run_id=run_id,
                uid=uid,
                query_params={SUBMIT_AFTER_LOGIN_Q: "1"},
            )
            # language=HTML
            error_msg = f"""
<p data-{SUBMIT_AFTER_LOGIN_Q}>
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
        seed = gui.session_state.get("seed")
        if not seed:
            return
        gooey_rng.seed(seed)

    def clear_outputs(self):
        # clear error msg
        gui.session_state.pop(StateKeys.error_msg, None)
        # clear outputs
        for field_name in self.ResponseModel.__fields__:
            gui.session_state.pop(field_name, None)

    def _render_after_output(self):
        self._render_report_button()

        if "seed" in self.RequestModel.schema_json():
            randomize = gui.button(
                '<i class="fa-solid fa-recycle"></i> Regenerate', type="tertiary"
            )
            if randomize:
                gui.session_state[StateKeys.pressed_randomize] = True
                gui.rerun()

    @classmethod
    def load_state_from_sr(cls, sr: SavedRun) -> dict:
        state = sr.to_dict()
        if state is None:
            raise HTTPException(status_code=404)
        return cls.load_state_defaults(state)

    @classmethod
    def load_state_defaults(cls, state: dict):
        for k, v in cls.RequestModel.schema()["properties"].items():
            try:
                state.setdefault(k, copy(v["default"]))
            except KeyError:
                pass
        for k, v in cls.sane_defaults.items():
            state.setdefault(k, v)
        return state

    def fields_to_save(self) -> list[str]:
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

    def _unsaved_state(self) -> dict[str, typing.Any]:
        result = {}
        for field in self.fields_not_to_save():
            try:
                result[field] = gui.session_state[field]
            except KeyError:
                pass
        return result

    def fields_not_to_save(self) -> list[str]:
        return []

    def _examples_tab(self):
        allow_hide = self.is_current_user_admin()

        def _render(pr: PublishedRun):
            self._render_example_preview(
                published_run=pr,
                allow_hide=allow_hide,
            )

        example_runs = (
            PublishedRun.objects.filter(
                workflow=self.workflow,
                visibility=PublishedRunVisibility.PUBLIC,
                is_approved_example=True,
            )
            .exclude(published_run_id="")
            .order_by("-example_priority", "-updated_at")[:50]
        )

        grid_layout(3, example_runs, _render)

    def _saved_tab(self):
        self.ensure_authentication()

        published_runs = PublishedRun.objects.filter(
            workflow=self.workflow,
            created_by=self.request.user,
        )[:50]
        if not published_runs:
            gui.write("No published runs yet")
            return

        def _render(pr: PublishedRun):
            with gui.div(className="mb-2", style={"font-size": "0.9rem"}):
                gui.pill(
                    PublishedRunVisibility(pr.visibility).get_badge_html(),
                    unsafe_allow_html=True,
                    className="border border-dark",
                )

            self.render_published_run_preview(published_run=pr)

        grid_layout(3, published_runs, _render)

    def _history_tab(self):
        self.ensure_authentication(anon_ok=True)

        uid = self.request.user.uid
        if self.is_current_user_admin():
            uid = self.request.query_params.get("uid", uid)

        before = gui.get_query_params().get("updated_at__lt", None)
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
            gui.write("No history yet")
            return

        grid_layout(3, run_history, self._render_run_preview)

        next_url = self.current_app_url(
            RecipeTabs.history,
            query_params={"updated_at__lt": run_history[-1].to_dict()["updated_at"]},
        )
        with gui.link(to=str(next_url)):
            gui.html(
                # language=HTML
                f"""<button type="button" class="btn btn-theme">Load More</button>"""
            )

    def ensure_authentication(self, next_url: str | None = None, anon_ok: bool = False):
        if not self.request.user or (self.request.user.is_anonymous and not anon_ok):
            raise gui.RedirectException(self.get_auth_url(next_url))

    def get_auth_url(self, next_url: str | None = None) -> str:
        from routers.root import login

        next_url = str(furl(next_url or self.request.url).set(origin=None))
        return str(furl(get_route_path(login), query_params=dict(next=next_url)))

    def _render_run_preview(self, saved_run: SavedRun):
        published_run: PublishedRun | None = (
            saved_run.parent_version.published_run if saved_run.parent_version else None
        )
        is_latest_version = published_run and published_run.saved_run == saved_run
        tb = get_title_breadcrumbs(self, sr=saved_run, pr=published_run)

        with gui.link(to=saved_run.get_app_url()):
            with gui.div(className="mb-1", style={"fontSize": "0.9rem"}):
                if is_latest_version:
                    gui.pill(
                        PublishedRunVisibility(
                            published_run.visibility
                        ).get_badge_html(),
                        unsafe_allow_html=True,
                        className="border border-dark",
                    )

            gui.write(f"#### {tb.h1_title}")

        updated_at = saved_run.updated_at
        if (
            updated_at
            and isinstance(updated_at, datetime.datetime)
            and not saved_run.run_status
        ):
            gui.caption("Loading...", **render_local_dt_attrs(updated_at))

        if saved_run.run_status:
            started_at_text(saved_run.created_at)
            html_spinner(saved_run.run_status, scroll_into_view=False)
        elif saved_run.error_msg:
            gui.error(saved_run.error_msg, unsafe_allow_html=True)

        return self.render_example(saved_run.to_dict())

    def render_published_run_preview(self, published_run: PublishedRun):
        tb = get_title_breadcrumbs(self, published_run.saved_run, published_run)
        with gui.link(to=published_run.get_app_url()):
            gui.write(f"#### {tb.h1_title}")

        with gui.div(className="d-flex align-items-center justify-content-between"):
            with gui.div():
                updated_at = published_run.saved_run.updated_at
                if updated_at and isinstance(updated_at, datetime.datetime):
                    gui.caption("Loading...", **render_local_dt_attrs(updated_at))

            if published_run.visibility == PublishedRunVisibility.PUBLIC:
                run_icon = '<i class="fa-regular fa-person-running"></i>'
                run_count = format_number_with_suffix(published_run.get_run_count())
                gui.caption(f"{run_icon} {run_count} runs", unsafe_allow_html=True)

        if published_run.notes:
            gui.caption(published_run.notes, line_clamp=2)

        doc = published_run.saved_run.to_dict()
        self.render_example(doc)

    def _render_example_preview(
        self,
        *,
        published_run: PublishedRun,
        allow_hide: bool,
    ):
        tb = get_title_breadcrumbs(self, published_run.saved_run, published_run)

        if published_run.created_by:
            with gui.div(className="mb-1 text-truncate", style={"height": "1.5rem"}):
                self.render_author(
                    published_run.created_by,
                    image_size="20px",
                    text_size="0.9rem",
                )

        with gui.link(to=published_run.get_app_url()):
            gui.write(f"#### {tb.h1_title}")

        with gui.div(className="d-flex align-items-center justify-content-between"):
            with gui.div():
                updated_at = published_run.saved_run.updated_at
                if updated_at and isinstance(updated_at, datetime.datetime):
                    gui.caption("Loading...", **render_local_dt_attrs(updated_at))

            run_icon = '<i class="fa-regular fa-person-running"></i>'
            run_count = format_number_with_suffix(published_run.get_run_count())
            gui.caption(f"{run_icon} {run_count} runs", unsafe_allow_html=True)

        if published_run.notes:
            gui.caption(published_run.notes, line_clamp=2)

        if allow_hide:
            self._example_hide_button(published_run=published_run)

        doc = published_run.saved_run.to_dict()
        self.render_example(doc)

    def _example_hide_button(self, published_run: PublishedRun):
        pressed_delete = gui.button(
            "🙈️ Hide",
            key=f"delete_example_{published_run.published_run_id}",
            style={"color": "red"},
        )
        if not pressed_delete:
            return
        self.set_hidden(published_run=published_run, hidden=True)

    def set_hidden(self, *, published_run: PublishedRun, hidden: bool):
        with gui.spinner("Hiding..."):
            published_run.is_approved_example = not hidden
            published_run.save()

        gui.rerun()

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

    # this is mostly depreated in favour of PublishedRun.notes
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

        gui.markdown(
            f'📖 To learn more, take a look at our <a href="{api_docs_url}" target="_blank">complete API</a>',
            unsafe_allow_html=True,
        )

        gui.write("#### 📤 Example Request")

        include_all = gui.checkbox("##### Show all fields")
        as_async = gui.checkbox("##### Run Async")
        as_form_data = gui.checkbox("##### Upload Files via Form Data")

        pr = self.get_current_published_run()
        api_url, request_body = self.get_example_request(
            gui.session_state,
            include_all=include_all,
            pr=pr,
        )
        response_body = self.get_example_response_body(
            gui.session_state, as_async=as_async, include_all=include_all
        )

        api_example_generator(
            api_url=api_url,
            request_body=request_body | self._unsaved_state(),
            as_form_data=as_form_data,
            as_async=as_async,
        )
        gui.write("")

        gui.write("#### 🎁 Example Response")
        gui.json(response_body, expanded=True)

        if not self.request.user or self.request.user.is_anonymous:
            gui.write("**Please Login to generate the `$GOOEY_API_KEY`**")
            return

        gui.write("---")
        with gui.tag("a", id="api-keys"):
            gui.write("### 🔐 API keys")

        manage_api_keys(self.request.user)

    def ensure_credits_and_auto_recharge(self, sr: SavedRun, state: dict):
        if not settings.CREDITS_TO_DEDUCT_PER_RUN:
            return
        assert self.request, "request must be set to check credits"
        assert self.request.user, "request.user must be set to check credits"

        user = self.request.user
        price = self.get_price_roundoff(state)

        if user.balance >= price:
            return

        if should_attempt_auto_recharge(user):
            yield "Low balance detected. Recharging..."
            run_auto_recharge_gracefully(user)
            user.refresh_from_db()

        if user.balance >= price:
            return

        raise InsufficientCredits(self.request.user, sr)

    def deduct_credits(self, state: dict) -> tuple[AppUserTransaction, int]:
        assert (
            self.request and self.request.user
        ), "request.user must be set to deduct credits"

        amount = self.get_price_roundoff(state)
        txn = self.request.user.add_balance(-amount, f"gooey_in_{uuid.uuid1()}")
        return txn, amount

    def get_price_roundoff(self, state: dict) -> int:
        multiplier = self.workflow.get_or_create_metadata().price_multiplier
        price = math.ceil(float(self.get_raw_price(state)) * multiplier)
        # don't allow fractional pricing for now, min 1 credit
        return max(1, price)

    def get_raw_price(self, state: dict) -> float:
        return self.price * (state.get("num_outputs") or 1)

    def get_total_linked_usage_cost_in_credits(self, default=1):
        """Return the sum of the linked usage costs in gooey credits."""
        sr = self.get_current_sr()
        total = sr.usage_costs.aggregate(total=Sum("dollar_amount"))["total"]
        if not total:
            return default
        return total * settings.ADDON_CREDITS_PER_DOLLAR

    def get_grouped_linked_usage_cost_in_credits(self):
        """Return the linked usage costs grouped by model name in gooey credits."""
        qs = (
            self.get_current_sr()
            .usage_costs.values("pricing__model_name")
            .annotate(total=Sum("dollar_amount") * settings.ADDON_CREDITS_PER_DOLLAR)
        )
        return {item["pricing__model_name"]: item["total"] for item in qs}

    @classmethod
    def get_example_preferred_fields(cls, state: dict) -> list[str]:
        """
        Fields that are not required, but are preferred to be shown in the example.
        """
        return []

    @classmethod
    def get_example_request(
        cls,
        state: dict,
        pr: PublishedRun | None = None,
        include_all: bool = False,
    ) -> tuple[furl, dict[str, typing.Any]]:
        api_url = cls.api_url(
            example_id=pr and pr.published_run_id, run_id=None, uid=None
        )
        fields = extract_model_fields(
            model=cls.RequestModel,
            state=state,
            include_all=include_all,
            preferred_fields=cls.get_example_preferred_fields(state),
            diff_from=pr.saved_run.to_dict() if pr else None,
        )
        return api_url, fields

    def get_example_response_body(
        self,
        state: dict,
        as_async: bool = False,
        include_all: bool = False,
    ) -> dict:
        run_id = get_random_doc_id()
        created_at = gui.session_state.get(
            StateKeys.created_at, datetime.datetime.utcnow().isoformat()
        )
        web_url = self.app_url(
            run_id=run_id,
            uid=self.request.user and self.request.user.uid,
        )
        sr = self.get_current_sr()
        output = sr.api_output(extract_model_fields(self.ResponseModel, state))
        if as_async:
            return dict(
                run_id=run_id,
                web_url=web_url,
                created_at=created_at,
                run_time_sec=gui.session_state.get(StateKeys.run_time, 0),
                status="completed",
                output=output,
            )
        else:
            return dict(
                id=run_id,
                url=web_url,
                created_at=created_at,
                output=output,
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


def started_at_text(dt: datetime.datetime):
    with gui.div(className="d-flex"):
        text = "Started"
        if seed := gui.session_state.get("seed"):
            text += f' with seed <span style="color: black;">{seed}</span>'
        gui.caption(text + " on&nbsp;", unsafe_allow_html=True)
        gui.caption(
            "...",
            className="text-black",
            **render_local_dt_attrs(dt),
        )


def render_output_caption():
    caption = ""

    run_time = gui.session_state.get(StateKeys.run_time, 0)
    if run_time:
        caption += f'Generated in <span style="color: black;">{run_time :.1f}s</span>'

    if seed := gui.session_state.get("seed"):
        caption += f' with seed <span style="color: black;">{seed}</span> '

    updated_at = gui.session_state.get(StateKeys.updated_at, datetime.datetime.today())
    if updated_at:
        if isinstance(updated_at, str):
            updated_at = datetime.datetime.fromisoformat(updated_at)
        caption += " on&nbsp;"

    with gui.div(className="d-flex"):
        gui.caption(caption, unsafe_allow_html=True)
        if updated_at:
            gui.caption(
                "...",
                className="text-black",
                **render_local_dt_attrs(
                    updated_at,
                    date_options={"month": "short", "day": "numeric"},
                ),
            )


def extract_model_fields(
    model: typing.Type[BaseModel],
    state: dict,
    include_all: bool = True,
    preferred_fields: list[str] = None,
    diff_from: dict | None = None,
) -> dict:
    """
    Include a field in result if:
    - include_all is true
    - field is required
    - field is preferred
    - diff_from is provided and field value differs from diff_from
    """
    return {
        field_name: state.get(field_name)
        for field_name, field in model.__fields__.items()
        if (
            include_all
            or field.required
            or (preferred_fields and field_name in preferred_fields)
            or (diff_from and state.get(field_name) != diff_from.get(field_name))
        )
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


class TitleValidationError(Exception):
    pass
