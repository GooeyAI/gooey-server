import datetime
import hashlib
import html
import inspect
import itertools
import json
import math
import traceback
import typing
import uuid
from copy import copy, deepcopy
from enum import Enum
from functools import cached_property
from itertools import pairwise
from random import Random
from textwrap import dedent
from time import sleep

import sentry_sdk
import yarl
from django.db.models import Q, Sum
from django.utils.text import slugify
from fastapi import HTTPException
from furl import furl
from pydantic import BaseModel, Field, ValidationError
from sentry_sdk.tracing import TRANSACTION_SOURCE_ROUTE
from starlette.datastructures import URL

import gooey_gui as gui
from ai_models.llm_openapi import patch_ai_model_schema_enums
from app_users.models import AppUser, AppUserTransaction
from auth.token_authentication import DISABLED_ACCOUNT_ERROR_MESSAGE
from bots.models import (
    PublishedRun,
    PublishedRunVersion,
    RetentionPolicy,
    SavedRun,
    Workflow,
    WorkflowAccessLevel,
)
from bots.models.published_run import Tag
from daras_ai.image_input import truncate_text_words
from daras_ai_v2 import exceptions, icons, settings
from daras_ai_v2.api_examples_widget import api_example_generator
from daras_ai_v2.breadcrumbs import get_title_breadcrumbs
from daras_ai_v2.copy_to_clipboard_button_widget import copy_to_clipboard_button
from daras_ai_v2.crypto import get_random_doc_id
from daras_ai_v2.github_tools import github_url_for_file
from daras_ai_v2.gooey_builder import (
    GOOEY_BUILDER_EVENT_KEY,
    GOOEY_BUILDER_TITLE,
    builder_thread_is_empty,
    can_launch_gooey_builder,
    get_gooey_builder_photo_url,
    render_gooey_builder,
)
from daras_ai_v2.grid_layout_widget import grid_layout
from daras_ai_v2.html_spinner_widget import html_spinner
from daras_ai_v2.manage_api_keys_widget import manage_api_keys
from daras_ai_v2.openapi_tricks import (
    get_full_pydantic_schema,
)
from daras_ai_v2.preview_img import media_preview_img
from daras_ai_v2.query_params_util import extract_query_params
from daras_ai_v2.ratelimits import RateLimitExceeded, ensure_rate_limits
from daras_ai_v2.send_email import send_reported_run_email
from daras_ai_v2.tab_spec import PaneSpec, RecipeView, TabSpec

# a leaf module - pydantic models only - so there is no cycle to dodge with a lazy import
from gooey_gui.types.recipe_top_bar_props import (
    RecipeTopBarProps,
    TopBarAuthor,
    TopBarIntegration,
    TopBarView,
)
from daras_ai_v2.urls import paginate_button, paginate_queryset
from daras_ai_v2.user_date_widgets import render_local_dt_attrs
from daras_ai_v2.utils import get_relative_time
from daras_ai_v2.variables_widget import variables_input
from functions.base_llm_tool import (
    BaseLLMTool,
    call_recipe_functions,
    functions_input,
    get_workflow_tools_from_state,
)
from functions.composio_tools import ComposioLLMTool
from functions.inbuilt_tools import get_inbuilt_tools
from functions.memory_tools import GooeyMemoryLLMTool
from functions.models import (
    FunctionScopes,
    FunctionTrigger,
    RecipeFunction,
    VariableSchema,
)
from functions.workflow_tools import WorkflowLLMTool
from gooeysite.custom_create import get_or_create_lazy
from payments.auto_recharge import (
    run_auto_recharge_gracefully,
    should_attempt_auto_recharge,
)
from payments.plans import PricingPlan
from routers.base_auth import get_login_url
from routers.root import RecipeTabs
from widgets.author import render_author_from_user
from widgets.base_header import render_help_button
from widgets.publish_form import clear_publish_form
from widgets.saved_workflow import render_saved_workflow_preview
from widgets.sidebar import sidebar_layout
from widgets.workflow_image import (
    render_change_notes_input,
    render_workflow_photo_uploader,
)
from widgets.workflow_share import render_share_button, render_share_modal
from workspaces.models import Workspace, WorkspaceMembership
from workspaces.widgets import (
    get_current_workspace,
    render_create_workspace_alert,
    set_current_workspace,
)

MAX_SEED = 4294967294
gooey_rng = Random()

SUBMIT_AFTER_LOGIN_Q = "submitafterlogin"
PUBLISH_AFTER_LOGIN_Q = "publishafterlogin"

STARTING_STATE = "Starting..."

# Reading width for the working column when it has the row to itself (the Config tab). Split
# needs none - the preview column caps it there.
SOLO_COL_MAX_WIDTH = "56rem"


def format_credits_as_dollars(credits: int) -> str:
    """A credit count as the price a user pays for it.

    `ADDON_CREDITS_PER_DOLLAR` is the one conversion rate in the codebase - at its default of
    100 a credit is exactly a cent - so prices shown here always agree with what billing
    charges, whatever the rate is set to.
    """
    return f"${credits / settings.ADDON_CREDITS_PER_DOLLAR:.2f}"


class RecipeRunState(Enum):
    standby = "standby"
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


class BasePageRequest:
    user: AppUser | None
    session: dict
    query_params: dict[str, str]
    url: URL | None


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
            None,
            title="🛠️ Developer Tools and Functions",
        )
        variables: dict[str, typing.Any] | None = Field(
            None,
            title="⌥ Variables",
            description="Variables to be used as Jinja prompt templates and in functions as arguments",
        )
        variables_schema: dict[str, VariableSchema] | None = Field(
            None,
            title="Variables Schema",
            description="Schema for variables to be used in the variables input",
        )

    ResponseModel: typing.Type[BaseModel]

    price = settings.CREDITS_TO_DEDUCT_PER_RUN
    price_deferred: bool = False

    def __init__(
        self,
        *,
        tab: RecipeTabs = RecipeTabs.run,
        request: BasePageRequest | None = None,
        user: AppUser | None = None,
        request_session: dict | None = None,
        request_url: URL | None = None,
        query_params: dict[str, str] | None = None,
    ):
        if request_session is None:
            request_session = {}
        if query_params is None:
            query_params = {}

        if request is None:
            request = BasePageRequest()
            request.user = user
            request.session = request_session
            request.query_params = query_params
            request.url = request_url

        self.tab = tab
        self.request = request

    @classmethod
    def canonical_slug(cls) -> str:
        return cls.slug_versions[-1]

    def current_app_url(
        self,
        tab: RecipeTabs = RecipeTabs.run,
        *,
        query_params: dict[str, str] | None = None,
        path_params: dict | None = None,
    ) -> str:
        if query_params is None:
            query_params = {}
        example_id, run_id, uid = extract_query_params(self.request.query_params)
        return self.app_url(
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
        tab: RecipeTabs | None = None,
        example_id: str | None = None,
        run_id: str | None = None,
        uid: str | None = None,
        query_params: dict[str, str] | None = None,
        path_params: dict | None = None,
    ) -> str:
        if query_params is None:
            query_params = {}

        if run_id and uid:
            query_params |= dict(run_id=run_id, uid=uid)
        q_example_id = query_params.pop("example_id", None)

        # old urls had example_id as a query param
        example_id = example_id or q_example_id
        run_slug: str | None = None
        if example_id:
            try:
                pr = cls.get_pr_from_example_id(example_id=example_id)
            except PublishedRun.DoesNotExist:
                pr = None
            if pr and pr.title:
                run_slug = slugify(pr.title)

        return cls.raw_app_url(
            query_params=query_params,
            example_id=example_id,
            run_slug=run_slug,
            tab=tab,
            path_params=path_params,
        )

    @classmethod
    def raw_app_url(
        cls,
        *,
        query_params: dict | None = None,
        example_id: str | None = None,
        run_slug: str | None = None,
        tab: RecipeTabs | None = None,
        path_params: dict | None = None,
    ):
        if not tab:
            tab = RecipeTabs.run
        url = yarl.URL(settings.APP_BASE_URL) / tab.url_path(
            page_slug=cls.canonical_slug(),
            run_slug=run_slug,
            example_id=example_id,
            **(path_params or {}),
        ).lstrip("/")
        if query_params:
            url = url.with_query(
                {k: v for (k, v) in query_params.items() if v is not None}
            )
        return str(url)

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
        return (
            furl(settings.API_BASE_URL, query_params=query_params)
            / "v2"
            / cls.canonical_slug()
        )

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
                "/" + self.canonical_slug(), source=TRANSACTION_SOURCE_ROUTE
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
                tab=self.tab, query_params=dict(self.request.query_params)
            )
        return event

    def sentry_event_set_user(self, event, hint):
        if user := self.request.user:
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
                        "disable_safety_checker",
                        "disable_rate_limits",
                        "created_at",
                    ]
                },
            }
            event.setdefault("tags", {}).update(
                user_is_paying=user.is_paying,
                user_is_anonymous=user.is_anonymous,
                user_is_disabled=user.is_disabled,
            )
        return event

    def load_state(self):
        from recipes.VideoBots import VideoBotsPage

        if not gui.session_state:
            gui.session_state.update(self.current_sr_to_session_state())

        is_running = gui.session_state.get(StateKeys.run_status)

        builder_sr = self.current_sr.parent_builder_saved_run
        is_builder_running = builder_sr and builder_sr.run_status

        if not (is_running or is_builder_running):
            gui.realtime_clear_subs()
            return

        sr = self.current_sr
        workflow_channel = self.realtime_channel_name(sr.run_id, sr.uid)

        if is_builder_running:
            builder_channel = VideoBotsPage.realtime_channel_name(
                builder_sr.run_id, builder_sr.uid
            )
            gui.realtime_pull([workflow_channel, builder_channel])

            new_state = self.current_sr_to_session_state()
            for k in ["--prev-request-hash"]:
                try:
                    new_state[k] = gui.session_state[k]
                except KeyError:
                    pass
            gui.session_state.clear()
            gui.session_state.update(new_state)
        else:
            output = gui.realtime_pull([workflow_channel])[0]
            if output:
                gui.session_state.update(output)

    def render_unauthorized(self, owner_workspace: Workspace | None = None):
        with gui.div(className="d-flex flex-column align-items-center"):
            gui.write(f"# {icons.lock}", unsafe_allow_html=True)
            gui.caption("Welcome to Gooey.AI")
            gui.write("# You need access")
            if not self.request.user or self.request.user.is_anonymous:
                gui.write(f"[Sign in]({self.get_auth_url()}) to view this resource.")
            else:
                if owner_workspace is None:
                    if self.current_pr.saved_run == self.current_sr:
                        owner_workspace = self.current_pr.workspace
                    else:
                        owner_workspace = self.current_sr.workspace
                gui.write(
                    dedent(f"""
                You currently don't have access to this resource. Please request access from the
                {owner_workspace.display_name(current_user=self.request.user)} admin or sign in with another account. 
                You are logged in as {self.request.user.email or self.request.user.phone_number}.
                """)
                )

    def render(self):
        if not self.is_user_authorized(self.request.user):
            self.render_unauthorized()
            return

        self.setup_sentry()

        self._user_disabled_check()
        self._check_if_flagged()

        if self.should_publish_after_login():
            self.publish_and_redirect()
        if self.should_submit_after_login():
            self.submit_and_redirect()

        if gui.session_state.get("show_report_workflow"):
            self.render_report_form()
            return

        tabs = self.get_tab_spec()
        assert tabs, f"{type(self).__name__}.get_tab_spec() returned no tabs"

        # App shell: the bar is a fixed-height row at the top and the body takes the rest of
        # the viewport, scrolling inside itself. The page as a whole never scrolls, so the
        # bar cannot slide out of view.
        #
        # The bar's node is reserved first (so it comes first in the DOM) but filled last:
        # _has_request_changed() - and so the publish state - is only settled once the inputs
        # have rendered. v1 renders its header last for the same reason.
        top_bar_placeholder = gui.div(
            className=(
                # v2-topbar-container makes this a CSS query container, so the bar's chips size
                # themselves against the bar's own width rather than the viewport's - the two
                # differ whenever the Builder is open or the rail is expanded
                "v2-topbar-container flex-shrink-0 w-100 border-bottom "
                "px-2 px-lg-4 py-2"
            )
        )

        # The Builder sits *beside* the tab body rather than wrapping the whole page, which
        # is what lets the bar above run the full width. v1 wraps the page instead, so the
        # shell skips its own sidebar_layout for v2 pages.
        # The Sidebar component's root is `h-100`, so it needs a parent with a definite
        # height to resolve against - as a bare flex child next to the bar it would resolve
        # to the full column and overflow by the bar's height.
        # v2-app-shell marks this as the shell the Builder panel lives *inside*, so its CSS
        # can drop `.gooey-sidebar`'s `height: 100dvh` - see RecipeTopBar.css
        with gui.div(
            className="v2-app-shell d-flex flex-column flex-grow-1 w-100",
            style=dict(minHeight=0),
        ):
            builder_pane, body_pane = self._builder_layout()

        with (
            body_pane,
            gui.div(
                className=(
                    # h-100 rather than flex-grow-1: the Sidebar puts three elements between
                    # this and the flex column above, and the nearest parent is a plain
                    # block, so there is no flex context left to grow into.
                    # px-lg-3 rather than px-4: the working column adds no gutter of its own,
                    # so the page's padding is the whole left margin the panes get.
                    "v2-workspace-body d-flex flex-column h-100 w-100 overflow-auto "
                    "px-2 px-lg-3 pt-2 pt-lg-1 pb-1 pb-lg-2"
                ),
                # without this a flex child refuses to shrink below its content, and the
                # overflow lands on the page instead of here
                style=dict(minHeight=0),
            ),
        ):
            if self.tab in {RecipeTabs.run, RecipeTabs.preview}:
                self._render_workspace(tabs)
            else:
                self.render_selected_tab()

        if builder_pane is not None:
            with builder_pane:
                self._render_gooey_builder()

        with top_bar_placeholder:
            self._render_top_bar(tabs=tabs)

        self._handle_top_bar_actions()

    def _render_workspace(self, tabs: list[TabSpec]):
        """Render each reusable work surface once; React controls their arrangement."""
        initial_view = self.entry_tab_slug(tabs)
        with gui.component(
            "RecipeWorkspace",
            storage_key=self._workspace_storage_key(),
            initial_view=initial_view,
        ):
            # mt-1 on the About card and the preview, not on the editor: those two are framed
            # surfaces that would otherwise sit flush against the top bar's rule, while the
            # editor leads with the pane strip, which brings its own spacing.
            with gui.div(className="mt-1"):
                with gui.styled(ABOUT_CSS), gui.div(className="v2-about"):
                    self._render_about_content()

            with gui.div():
                if self._render_deleted_output_if_needed():
                    submitted = False
                else:
                    submitted = self._render_solo_input_col()

            with gui.div(className="mt-1"):
                if self.current_sr.retention_policy == RetentionPolicy.delete:
                    self.render_deleted_output()
                else:
                    self._render_output_col(submitted=submitted)

    def _workspace_storage_key(self) -> str:
        return (
            f"gooey:recipe-layout:{self.workflow.value}:"
            f"{self.current_pr.published_run_id}"
        )

    def _can_show_builder(self) -> bool:
        try:
            workspace = self.current_workspace
        except Workspace.DoesNotExist:
            return False
        return can_launch_gooey_builder(self.request, workspace)

    def _builder_layout(self):
        """(builder pane, body pane) - the Builder beside the tab body, not around it.

        Returns `(None, dummy)` when the Builder is unavailable, so the body renders with
        no extra wrapper at all rather than an empty sidebar.
        """
        if not self._can_show_builder():
            return None, gui.dummy()

        return sidebar_layout(
            key=GOOEY_BUILDER_EVENT_KEY,
            session=self.request.session,
            disabled=False,
            client_only=True,
            storage_key=f"{self._workspace_storage_key()}:builder",
        )

    def _render_gooey_builder(self):
        # The panel's own collapse control, pinned to its top-right corner at every
        # breakpoint. Absolute against `.gooey-sidebar`, which is positioned either way
        # (sticky on desktop, fixed below the sidebar breakpoint), so there is no app-header
        # offset to hardcode. The shared React control supplies the same icon, dimensions,
        # and HTML tooltip as the editor and preview controls.
        gui.component(
            "WorkspacePaneControl",
            label="Close Ask gooey",
            icon=icons.cls.cancel,
            event_name=f"{GOOEY_BUILDER_EVENT_KEY}:close",
            className="v2-builder-close",
        )
        # The panel's title, opposite the close button. v2 hides the widget's own header, so
        # without this the panel is unnamed and there is no way to start a fresh conversation
        # from it. GooeyBuilderInlineEmbed turns the event into its `onNewConversation`.
        #
        # Hidden on an empty thread: the widget draws its own logo-and-title splash there, so
        # this would be a second copy of the same name - and "New Chat" is a no-op on a chat
        # that has not started.
        if not builder_thread_is_empty(self):
            gui.component(
                "WorkspacePaneControl",
                label=GOOEY_BUILDER_TITLE,
                # the label names the panel; the tooltip says what clicking it does
                tooltip="New Chat",
                photo_url=get_gooey_builder_photo_url(),
                show_label=True,
                event_name=f"{GOOEY_BUILDER_EVENT_KEY}:new",
                # no Bootstrap padding utility here: `.v2-pane-control-labelled` owns this
                # button's padding, and `p-2` competed with it on equal specificity, so which
                # one won came down to stylesheet order
                className="v2-builder-new",
            )
        render_gooey_builder(
            event_key=GOOEY_BUILDER_EVENT_KEY, request=self.request, page=self
        )

    def _handle_top_bar_actions(self):
        """Pop the keys RecipeTopBar wrote and act on them.

        The bar mutates session state and calls onChange(); the server sees the key on the
        next render. Same contract `handle_workspace_switch` uses for the sidebar.
        """
        publish_ref = gui.use_alert_dialog(key="publish-modal")

        if gui.session_state.pop(self.TOP_BAR_PUBLISH_KEY, None):
            if self.is_logged_in():
                clear_publish_form()
                publish_ref.set_open(True)
            else:
                self._publish_for_anonymous_user()

        if publish_ref.is_open:
            self._render_publish_dialog(ref=publish_ref)

        # the one Share dialog on the page: the bar's button and About's both set the key
        share_ref = gui.use_alert_dialog(key="share-modal")
        if gui.session_state.pop(self.TOP_BAR_SHARE_KEY, None):
            share_ref.set_open(True)
        if share_ref.is_open:
            render_share_modal(
                dialog=share_ref,
                publish_dialog_ref=publish_ref,
                user=self.request.user,
                pr=self.current_pr,
                current_app_url=self.current_app_url(self.tab),
                session=self.request.session,
            )

        if gui.session_state.pop(self.TOP_BAR_RUN_KEY, None):
            self._handle_top_bar_run()

    def _handle_top_bar_run(self):
        """Run (or Stop) pressed in the top bar.

        Same behaviour v1's submit button has, minus the button: validate first, surface the
        message and start nothing if validation fails, and let anonymous users through the
        login redirect that `submit_and_redirect` already handles.
        """
        if self._is_run_in_progress():
            self.current_sr.is_cancelled = True
            self.current_sr.save(update_fields=["is_cancelled", "updated_at"])
            raise gui.RerunException()

        try:
            self.validate_form_v2()
        except AssertionError as e:
            gui.error(str(e))
            return

        self.submit_and_redirect()

    def entry_tab_slug(self, tabs: list[TabSpec]) -> RecipeView:
        """Initial client view when this workflow has no stored pane layout."""
        return tabs[0].slug

    def is_unowned_example(self) -> bool:
        """The url points at a published workflow the viewer does not own, rather than at a
        run of it - an example, or the recipe's root. In other words, a first-time visitor.
        """
        sr, pr = self.current_sr_pr
        return pr.saved_run_id == sr.id and not self.is_current_user_owner()

    # keys the RecipeTopBar writes into session state; popped by _handle_top_bar_actions
    TOP_BAR_MENU_KEY = "--topbar-menu"
    TOP_BAR_PUBLISH_KEY = "--topbar-publish"
    TOP_BAR_RUN_KEY = "--topbar-run"
    TOP_BAR_SHARE_KEY = "--topbar-share"

    def can_manage_sharing(self) -> bool:
        """Whether this user may change who can see the workflow, rather than only copy
        its url.

        Deliberately *not* v1's condition: `render_share_button` also requires the url to
        point at the published run itself, so v1 hides Share the moment you open a run. The
        dialog only ever edits `pr`, which is the same object either way, and it gates its
        own options by role - so being on a run is no reason to lose the control.
        """
        pr = self.current_pr
        user = self.request.user
        # render_share_modal asserts both of these
        if not user or not pr.workspace_id:
            return False
        if pr.is_root():
            # the recipe's own template: sharing it is not a user's call
            return False
        if user.is_admin():
            return True
        try:
            return self.current_workspace.id == pr.workspace_id
        except Workspace.DoesNotExist:
            return False

    def _render_share_trigger(self, *, key: str, className: str = "mb-0"):
        """Share, wherever it appears outside the top bar.

        It only sets the key the bar's Share menu item sets - `_handle_top_bar_actions` owns
        the one dialog, so two triggers can never render two of them.
        """
        if not self.can_manage_sharing():
            copy_to_clipboard_button(
                label=f"{icons.link} Share",
                value=self.current_app_url(self.tab),
                type="secondary",
                className=className,
            )
            return
        if gui.button(
            f"{self.current_pr.get_share_icon()} Share",
            key=key,
            type="secondary",
            className=className,
        ):
            gui.session_state[self.TOP_BAR_SHARE_KEY] = True
            gui.rerun()

    # Not popped: unlike the others this is a standing fact about the client, not an
    # action. The bar keeps it current and `submit_and_redirect` reads it to decide
    # whether Split is on screen at all.
    TOP_BAR_WIDE_KEY = "--topbar-wide"

    def _top_bar_cost(self) -> tuple[str, str]:
        """(label, hover note) for the bar's cost readout, in dollars.

        The mock shows "$0.10 / 5g CO2". Only the dollars ship: credits convert exactly via
        ADDON_CREDITS_PER_DOLLAR, whereas nothing in this codebase can produce a CO2 figure,
        and inventing one would put a fabricated environmental claim in the product.
        """
        credits = self.get_run_cost_credits()
        if credits is None:
            # deferred pricing - show nothing rather than "$None"
            return "", ""

        label = format_credits_as_dollars(credits)

        notes = [n for n in (self.get_cost_note(), self.additional_notes()) if n]
        return label, " ".join(n.strip() for n in notes)

    def _top_bar_integrations(self) -> list[TopBarIntegration]:
        """Channel shortcuts for the bar's right cluster. Recipes with public deployments
        override this; most have none."""
        return []

    def _is_run_in_progress(self) -> bool:
        return bool(
            gui.session_state.get(StateKeys.run_status)
            and not self.current_sr.is_cancelled
            and (self.is_current_user_owner() or self.is_current_user_admin())
        )

    def _render_top_bar(self, *, tabs: list[TabSpec]):
        from widgets.workflow_image import CIRCLE_IMAGE_WORKFLOWS

        sr, pr = self.current_sr_pr
        tbreadcrumbs = get_title_breadcrumbs(self, sr, pr, tab=self.tab)
        cost_label, cost_title = self._top_bar_cost()

        gui.model_component(
            RecipeTopBarProps(
                title=tbreadcrumbs.title_with_prefix() or self.get_run_title(sr, pr),
                photo_url=pr.photo_url or None,
                circle_photo=self.workflow in CIRCLE_IMAGE_WORKFLOWS,
                author=self._top_bar_author(),
                storage_key=self._workspace_storage_key(),
                initial_view=self.entry_tab_slug(tabs),
                workspace_href=self.current_app_url(RecipeTabs.run),
                workspace_active=self.tab in {RecipeTabs.run, RecipeTabs.preview},
                views=[
                    TopBarView(
                        slug=tab.slug,
                        label=tab.label,
                        icon=tab.icon,
                        desktop_only=tab.desktop_only,
                        immersive_on_mobile=tab.immersive_on_mobile,
                    )
                    for tab in tabs
                ],
                publish_label=self._top_bar_publish_label(),
                publish_key=self.TOP_BAR_PUBLISH_KEY,
                api_href=self.current_app_url(RecipeTabs.run_as_api),
                share_key=(self.TOP_BAR_SHARE_KEY if self.can_manage_sharing() else ""),
                share_icon=icons.share,
                has_unpublished_changes=self._has_request_changed()
                or (self.can_user_save_run(sr, pr) and pr.saved_run != sr),
                menu_key=self.TOP_BAR_MENU_KEY,
                integrations=self._top_bar_integrations(),
                run_key=self.TOP_BAR_RUN_KEY,
                viewport_wide_key=self.TOP_BAR_WIDE_KEY,
                is_running=self._is_run_in_progress(),
                cost_label=cost_label,
                cost_href=self.get_credits_click_url(),
                cost_title=cost_title,
            )
        )

    def _top_bar_author(self):
        """The "by <someone>" line. Workspace when there is one, else the run's user."""

        pr = self.current_pr
        if pr.workspace_id and not pr.workspace.is_personal:
            return TopBarAuthor(
                label=f"by {pr.workspace.display_name(self.request.user)}",
                photo_url=pr.workspace.photo_url or None,
            )
        user = self.current_sr_user
        if user:
            return TopBarAuthor(
                label=f"by {user.display_name or user.first_name(fallback='User')}",
                photo_url=user.photo_url or None,
            )
        return None

    def _top_bar_publish_label(self) -> str:
        """Same permission-derived wording v1's save button uses."""
        if not self.is_logged_in():
            return "Save"
        if WorkflowAccessLevel.can_user_edit_published_run(
            workspace=self.current_workspace,
            user=self.request.user,
            pr=self.current_pr,
        ):
            return "Update"
        elif self._has_request_changed():
            return "Save and Run"
        else:
            return "Save as New"

    PANE_QUERY_PARAM = "pane"

    def _render_pane_strip(
        self, panes: list[PaneSpec], *, key: str
    ) -> typing.Callable[[], None]:
        """Render an in-page strip of panes and return the one to draw.

        Panes are panels inside a single view, so - unlike tabs - they have no url: just an
        ordered list of specs and a session-state key. Session state and deep links carry
        `PaneSpec.id`, never the label, so relabelling a pane cannot break a link to it.

        Only the active pane renders. That is safe because the server round-trips the whole
        `session_state` regardless of what was drawn, so widgets on the panes that did not
        render keep their values (see `gooey_gui/core/renderer.py`). The corollary is that a
        pane must never depend on another pane's *return value* - read `gui.session_state`.
        """
        by_id = {pane.id: pane for pane in panes}

        # A link from another view (About's meta cards) names its pane in the url, because
        # session state does not survive a navigation. Honour it once: `seen_key` stops it
        # overriding the strip on every later render, which would pin the pane forever.
        seen_key = key + ":from-url"
        requested = self.request.query_params.get(self.PANE_QUERY_PARAM)
        if requested in by_id and gui.session_state.get(seen_key) != requested:
            gui.session_state[key] = gui.session_state[seen_key] = requested
        elif gui.session_state.get(key) not in by_id:
            gui.session_state[key] = panes[0].id

        with gui.styled(PANE_STRIP_CSS), gui.div(className="my-1"):
            for pane in panes:
                is_active = pane.id == gui.session_state[key]
                if gui.button(
                    pane.label,
                    key=f"{key}:{pane.id}",
                    type="tertiary",
                    className="pane-active" if is_active else "",
                ):
                    gui.session_state[key] = pane.id
                    gui.rerun()

        return by_id[gui.session_state[key]].render

    def render_header_extra(self):
        pass

    def can_user_save_run(
        self,
        current_run: SavedRun,
        published_run: PublishedRun,
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
                and self.request.user
                and WorkflowAccessLevel.can_user_edit_published_run(
                    workspace=self.current_workspace,
                    user=self.request.user,
                    pr=published_run,
                )
            )
        )

    def _render_options_button_with_dialog(self):
        ref = gui.use_alert_dialog(key="options-modal")
        if gui.button(label=icons.more_options, className="mb-0", type="tertiary"):
            ref.set_open(True)
        if ref.is_open:
            with gui.alert_dialog(ref=ref, modal_title="### Options"):
                if (
                    self.request.user
                    and WorkflowAccessLevel.can_user_edit_published_run(
                        workspace=self.current_workspace,
                        user=self.request.user,
                        pr=self.current_pr,
                    )
                ):
                    self._saved_options_modal()
                else:
                    self._unsaved_options_modal()

    def render_social_buttons(self):
        with (
            gui.styled("& .btn { padding: 6px }"),
            gui.div(className="d-flex gap-lg-2 gap-1"),
        ):
            publish_dialog_ref = gui.use_alert_dialog(key="publish-modal")

            if self.tab == RecipeTabs.run or self.tab == RecipeTabs.preview:
                if self.current_pr.is_root():
                    render_help_button(self.current_sr.get_workflow_metadata())
                if self.is_logged_in():
                    self._render_options_button_with_dialog()
                render_share_button(
                    publish_dialog_ref=publish_dialog_ref,
                    workspace_id=self.request.user and self.current_workspace.id,
                    user=self.request.user,
                    sr=self.current_sr,
                    pr=self.current_pr,
                    current_app_url=self.current_app_url(self.tab),
                    session=self.request.session,
                )
                self._render_save_button(publish_dialog_ref)
            elif self.tab != RecipeTabs.examples:
                copy_to_clipboard_button(
                    label=f"{icons.link} Copy Link",
                    value=self.current_app_url(self.tab),
                    type="secondary",
                    className="mb-0 px-2",
                )

            if publish_dialog_ref.is_open:
                self._render_publish_dialog(ref=publish_dialog_ref)

    def _render_save_button(self, publish_dialog_ref: gui.AlertDialogRef):
        with gui.div(className="d-flex justify-content-end"):
            if self.request.user and WorkflowAccessLevel.can_user_edit_published_run(
                workspace=self.current_workspace,
                user=self.request.user,
                pr=self.current_pr,
            ):
                icon, label = icons.save, "Update"
            elif self._has_request_changed():
                icon, label = icons.save, "Save and Run"
            else:
                icon, label = icons.fork, "Save as New"

            if gui.button(
                f'{icon} <span class="d-none d-lg-inline">{label}</span>',
                className="mb-0 px-3 px-lg-4",
                type="primary",
            ):
                if self.is_logged_in():
                    clear_publish_form()
                    publish_dialog_ref.set_open(True)
                else:
                    self._publish_for_anonymous_user()

    def _publish_for_anonymous_user(self):
        query_params = {PUBLISH_AFTER_LOGIN_Q: "1"}
        if self._has_request_changed():
            sr = self.create_and_validate_new_run(
                enable_rate_limits=True, run_status=None
            )
        else:
            sr = self.current_sr

        raise gui.RedirectException(
            self.get_auth_url(next_url=sr.get_app_url(query_params=query_params))
        )

    def _render_publish_dialog(self, *, ref: gui.AlertDialogRef):
        """
        Note: all input keys in this method should start with `published_run_*`
        (see: method clear_publish_form)
        """
        assert self.is_logged_in()

        sr = self.current_sr
        pr = self.current_pr

        if self.request.user and WorkflowAccessLevel.can_user_edit_published_run(
            workspace=self.current_workspace,
            user=self.request.user,
            pr=self.current_pr,
        ):
            label = "Update"
        elif self._has_request_changed():
            label = "Save and Run"
        else:
            label = "Save as New"

        with gui.alert_dialog(
            ref=ref,
            modal_title=f"### {label} Workflow",
            large=True,
        ):
            self._render_publish_form(sr=sr, pr=pr, dialog=ref)

    def _render_publish_form(
        self,
        sr: SavedRun,
        pr: PublishedRun,
        dialog: gui.AlertDialogRef,
    ):
        form_container = gui.div()

        with gui.div(
            className="mt-2 d-block d-lg-flex justify-content-between align-items-end"
        ):
            selected_workspace = self._render_workspace_selector(
                key="published_run_workspace"
            )

            user_can_edit = WorkflowAccessLevel.can_user_edit_published_run(
                workspace=selected_workspace,
                user=self.request.user,
                pr=pr,
            )
            with gui.div(className="mt-4 mt-lg-0 text-end"):
                if user_can_edit and pr.workspace_id == selected_workspace.id:
                    pressed_save_as_new = gui.button(
                        f"{icons.fork} Save as New",
                        type="secondary",
                        key="save_published_run_as_new",
                        className="mb-0 py-2 px-4",
                    )
                    pressed_save = gui.button(
                        f"{icons.save} Save",
                        type="primary",
                        key="save_published_run",
                        className="mb-0 ms-2 py-2 px-4",
                    )
                else:
                    pressed_save_as_new = gui.button(
                        f"{icons.fork} Save as New",
                        type="primary",
                        key="save_published_run",
                        className="mb-0 py-2 px-4",
                    )
                    pressed_save = False

        with form_container:
            if user_can_edit:
                title = self.get_run_title(self.current_sr, self.current_pr)
                notes = pr.notes
            else:
                title = self._get_default_pr_title()
                notes = ""

            col1, col2 = gui.columns([2, 1])
            with col1:
                gui.write("Title", className="fs-5 container-margin-reset")
                published_run_title = gui.text_input(
                    "",
                    key="published_run_title",
                    value=title,
                    className="mt-1",
                )
                gui.write("Description", className="fs-5 container-margin-reset")
                published_run_description = gui.text_area(
                    "",
                    key="published_run_description",
                    value=notes,
                    placeholder="An excellent but one line description",
                    className="mt-1",
                    rows=5,
                )
                with gui.div(className="d-flex align-items-center gap-2"):
                    change_notes = render_change_notes_input(
                        key="published_run_change_notes"
                    )
            with col2:
                photo_url = render_workflow_photo_uploader(
                    workspace=self.current_workspace,
                    user=self.request.user,
                    pr=pr,
                    title=published_run_title,
                    description=published_run_description,
                )

            with gui.div(className="d-flex mb-3 align-items-center gap-2"):
                options = {t.pk: t for t in Tag.get_options()}
                gui.write("Tags", className="fs-5 mb-3")
                if not isinstance(gui.session_state.get("published_run_tags"), list):
                    gui.session_state["published_run_tags"] = [
                        tag.pk for tag in pr.tags.all()
                    ]
                with gui.div(className="flex-grow-1"):
                    tag_pks = gui.multiselect(
                        label="",
                        options=options,
                        format_func=lambda pk: options[pk].render(),
                        key="published_run_tags",
                        allow_none=True,
                    )
                    tags = [options[pk] for pk in tag_pks]

        self._render_admin_options(sr, pr)

        # add friction for saving root workflows
        if pr.is_root():
            ref = gui.use_confirm_dialog("confirm-save-root")
            if pressed_save:
                ref.set_open(True)
            pressed_save = ref.pressed_confirm
            if ref.is_open:
                with gui.confirm_dialog(
                    ref=ref,
                    modal_title="### ⚠️ Are you sure?",
                    confirm_label=f"{icons.save} Save",
                    confirm_className="bg-danger border-danger text-light",
                ):
                    gui.write(
                        "You're about to update the root workflow as an admin.\n\n"
                        f'If you want to create a new example, press "{icons.fork} Save as New".',
                        unsafe_allow_html=True,
                    )

        if not pressed_save and not pressed_save_as_new:
            # neither action was taken - nothing to do now
            return

        if pressed_save_as_new and published_run_title == pr.title:
            published_run_title = f"{published_run_title} (Copy)"

        editing_root_published_run = pressed_save and user_can_edit and pr.is_root()
        if not editing_root_published_run:
            try:
                self._validate_published_run_title(published_run_title)
            except TitleValidationError as e:
                gui.error(str(e))
                return

        if self._has_request_changed():
            sr = self.on_submit()
            if not sr:
                dialog.set_open(False)
                raise gui.RerunException()

        if pressed_save_as_new:
            if (
                selected_workspace != self.current_workspace
                and selected_workspace in self.request.user.cached_workspaces
            ):
                set_current_workspace(self.request.session, selected_workspace.id)

            pr = self.create_published_run(
                published_run_id=get_random_doc_id(),
                saved_run=sr,
                user=self.request.user,
                workspace=selected_workspace,
                title=published_run_title.strip(),
                notes=published_run_description.strip(),
                photo_url=photo_url,
                tags=tags,
            )
        else:
            if not WorkflowAccessLevel.can_user_edit_published_run(
                workspace=selected_workspace,
                user=self.request.user,
                pr=self.current_pr,
            ):
                gui.error("You don't have permission to update this workflow")
                return
            updates = dict(
                saved_run=sr,
                title=published_run_title.strip(),
                notes=published_run_description.strip(),
                photo_url=photo_url,
                tags=tags,
            )
            if not self._has_published_run_changed(published_run=pr, **updates):
                gui.error("No changes to publish", icon="⚠️")
                return
            pr.add_version(
                user=self.request.user, change_notes=change_notes.strip(), **updates
            )
        raise gui.RedirectException(pr.get_app_url())

    def _get_workspace_options(self) -> dict[int, Workspace]:
        workspace_options = {w.id: w for w in self.request.user.cached_workspaces}
        if (
            self.current_pr.workspace_id
            and self.request.user
            and WorkflowAccessLevel.can_user_edit_published_run(
                workspace=self.current_pr.workspace,
                user=self.request.user,
                pr=self.current_pr,
            )
        ):
            # default to current_pr.workspace for an editor
            workspace_options = {
                self.current_pr.workspace_id: self.current_pr.workspace
            } | workspace_options
        else:
            # default to current workspace for everyone else
            workspace_options = {
                self.current_workspace.id: self.current_workspace
            } | workspace_options
        return workspace_options

    def _render_workspace_selector(self, *, key: str) -> "Workspace":
        workspace_options = self._get_workspace_options()

        if len(workspace_options) <= 1:
            render_create_workspace_alert()
            return self.current_workspace

        with gui.div(className="d-flex gap-3"):
            with gui.div(className="mt-2 text-nowrap"):
                gui.html("Workspace")

            with gui.div(style=dict(maxWidth="300px", width="100%")):
                workspace_id = gui.selectbox(
                    "",
                    key=key,
                    options=workspace_options,
                    format_func=lambda w_id: workspace_options[w_id].display_html(
                        self.request.user
                    ),
                    className="mb-0",
                )
                return workspace_options[workspace_id]

    def _get_default_pr_title(self):
        return f"{self.request.user.first_name_possesive()} {self.get_run_title(self.current_sr, self.current_pr)}"

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
        photo_url: str,
        tags: list[Tag] | None,
    ):
        return (
            published_run.title != title
            or published_run.notes != notes
            or published_run.saved_run != saved_run
            or published_run.photo_url != photo_url
            or set(published_run.tags.values_list("pk", flat=True))
            != {t.pk for t in (tags or [])}
        )

    def _has_request_changed(self) -> bool:
        if gui.session_state.get("--has-request-changed"):
            return True

        try:
            curr_req = self.RequestModel.model_validate(gui.session_state)
        except ValidationError:
            # if the request model fails to parse, the request has likely changed
            return True

        curr_hash = hashlib.md5(
            json.dumps(curr_req.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()
        prev_hash = gui.session_state.setdefault("--prev-request-hash", curr_hash)

        if curr_hash != prev_hash:
            gui.session_state["--has-request-changed"] = True  # cache it for next time
            return True
        else:
            return False

    def _saved_options_modal(self):
        assert self.is_logged_in()

        with gui.div(
            className="mb-3 d-flex justify-content-around align-items-center gap-3"
        ):
            is_latest_version = self.current_pr.saved_run == self.current_sr
            if is_latest_version:
                label = "Duplicate"
            else:
                label = "Save as New"
            save_as_new_button = gui.button(f"{icons.fork} {label}", className="w-100")

            if (
                self.request.user
                and WorkflowAccessLevel.can_user_delete_published_run(
                    workspace=self.current_workspace,
                    user=self.request.user,
                    pr=self.current_pr,
                )
                and not self.current_pr.is_root()
            ):
                ref = gui.use_confirm_dialog(key="--delete-run-modal")
                gui.button_with_confirm_dialog(
                    ref=ref,
                    trigger_label=f"{icons.trash} Delete",
                    trigger_className="w-100 text-danger",
                    modal_title="#### Are you sure?",
                    modal_content=f"""
    Are you sure you want to delete this published run?

    **{self.current_pr.title}**

    This will also delete all the associated versions.
                    """,
                    confirm_label="Delete",
                    confirm_className="border-danger bg-danger text-white",
                )
                if ref.pressed_confirm:
                    self.current_pr.delete()
                    raise gui.RedirectException(self.app_url())

        title = f"{self.current_pr.title} (Copy)"
        if self.current_pr.is_root():
            notes = ""
        else:
            notes = self.current_pr.notes

        if save_as_new_button:
            new_pr = self.create_published_run(
                published_run_id=get_random_doc_id(),
                saved_run=self.current_sr,
                user=self.request.user,
                workspace=self.current_workspace,
                tags=list(self.current_pr.tags.all()),
                title=title,
                notes=notes,
            )
            raise gui.RedirectException(
                self.app_url(example_id=new_pr.published_run_id)
            )

        with gui.div(className="mt-4"):
            with gui.div(className="mb-4"):
                gui.write(f"#### {icons.time} Version History", unsafe_allow_html=True)
            self._render_version_history()

    def _unsaved_options_modal(self):
        assert self.is_logged_in()

        gui.write(
            "Like this AI workflow? Duplicate and then customize it for your use case."
        )
        duplicate_button = gui.button(f"{icons.fork} Duplicate", className="w-100")
        if duplicate_button:
            pr = self.current_pr
            duplicate_pr = pr.duplicate(
                user=self.request.user,
                workspace=self.current_workspace,
                title=f"{self.request.user.first_name_possesive()} {pr.title}",
                notes=pr.notes,
            )
            raise gui.RedirectException(
                self.app_url(example_id=duplicate_pr.published_run_id)
            )

        gui.write("You can then collaborate on it by creating a Team Workspace.")

        github_url = github_url_for_file(inspect.getfile(self.__class__))
        gui.caption(
            "If you're geeky and want to contribute to the code behind this workflow, view it on "
            f'{icons.github_alt} <a href="{github_url}" target="_blank">GitHub</a>.',
            unsafe_allow_html=True,
        )

    def _render_admin_options(self, current_run: SavedRun, published_run: PublishedRun):
        if (
            not self.is_current_user_admin()
            or published_run.is_root()
            or published_run.saved_run != current_run
        ):
            return

        gui.newline()
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
                change_notes = gui.text_area(
                    "Change Notes",
                    key="change_notes",
                    value="",
                )
                if gui.button("👌 Yes, Update the Root Workflow"):
                    root_run = self.get_root_pr()
                    root_run.add_version(
                        user=self.request.user,
                        title=published_run.title,
                        notes=published_run.notes,
                        saved_run=published_run.saved_run,
                        public_access=WorkflowAccessLevel.FIND_AND_VIEW,
                        change_notes=change_notes,
                        tags=list(published_run.tags.all()),
                    )
                    raise gui.RedirectException(self.app_url())

    @classmethod
    def get_prompt_title(cls, sr: SavedRun) -> str | None:
        return truncate_text_words(
            cls.preview_input(sr.to_dict()) or "",
            maxlen=60,
        ).replace("\n", " ")

    @classmethod
    def get_run_title(cls, sr: SavedRun, pr: PublishedRun | None) -> str:
        return (pr and pr.title) or cls.get_recipe_title()

    @classmethod
    def get_recipe_title(cls) -> str:
        return cls.get_root_pr().title or cls.title or cls.workflow.label

    def get_explore_image(self) -> str:
        meta = self.workflow.get_or_create_metadata()
        img = meta.default_image or self.explore_image or ""
        return media_preview_img(img) or img

    def _user_disabled_check(self):
        if self.current_sr_user and self.current_sr_user.is_disabled:
            msg = DISABLED_ACCOUNT_ERROR_MESSAGE
            gui.error(msg, icon="😵")
            gui.stop()

    def get_tab_spec(self) -> list[TabSpec]:
        """The client views for this request, in selector order."""
        return [
            TabSpec(
                slug=RecipeView.about,
                label="About",
                icon=icons.info,
            ),
            TabSpec(
                slug=RecipeView.edit,
                label="Edit",
                icon=icons.edit,
            ),
            TabSpec(
                slug=RecipeView.preview,
                label="Preview",
                icon=icons.preview,
            ),
            TabSpec(
                slug=RecipeView.split,
                label="Split",
                icon=icons.run,
            ),
        ]

    def _render_about_content(self):
        """What this workflow is. The one surface in v2 that is not a re-slice of v1.

        Deliberately not here: version history, which lives in the title chevron menu, and
        Related Workflows, which is what /explore/ is for. About is about *this* workflow,
        and nothing on it is shown twice.
        """
        sr, pr = self.current_sr_pr
        with gui.div(className="v2-about-card"):
            # photo, title and byline are one row: the image identifies the workflow and the
            # title names it, so they belong on the same line rather than stacked with the
            # image taking a band of its own
            with gui.div(className="v2-about-head"):
                self._render_about_photo(pr)
                with gui.div(className="v2-about-headtext"):
                    gui.html(
                        f'<h1 class="v2-about-title">'
                        f"{html.escape(pr.title or self.title)}</h1>"
                    )
                    self._render_about_byline(sr, pr)
            # full text, unlike v1's `line_clamp=3` on the Run tab - the tab exists to be read
            if pr.notes:
                with gui.div(className="container-margin-reset v2-about-notes"):
                    gui.write(pr.notes)
            self._render_about_meta()

    def _render_about_photo(self, pr: PublishedRun):
        """The workflow's own image, beside the title - an avatar, not a banner.

        A workflow photo is a square-ish icon, so it is drawn at a fixed size either way and
        only its corner radius changes: `CIRCLE_IMAGE_WORKFLOWS` (agents) get the same round
        portrait the top bar and the rail already give them.
        """
        from widgets.workflow_image import CIRCLE_IMAGE_WORKFLOWS

        if not pr.photo_url:
            return
        circle = self.workflow in CIRCLE_IMAGE_WORKFLOWS
        gui.html(
            f'<img class="v2-about-photo{" v2-about-photo-circle" if circle else ""}"'
            f' src="{html.escape(pr.photo_url)}" alt="">'
        )

    def _render_about_byline(self, sr: SavedRun, pr: PublishedRun):
        """Who published this and how much else they have published, with Share opposite."""
        with gui.div(className="v2-about-byline"):
            workspace = pr.workspace
            if workspace:
                if photo := workspace.get_photo():
                    gui.html(
                        f'<img class="v2-about-byline-photo" src="{html.escape(photo)}" alt="">'
                    )
                with gui.div(className="v2-about-byline-text"):
                    gui.html(
                        f'<div class="v2-about-byline-name">'
                        f"{html.escape(workspace.display_name())}</div>"
                    )
                    count = self._public_workflow_count(workspace)
                    if count:
                        gui.html(
                            f'<div class="v2-about-byline-sub">{count} Public Workflows</div>'
                        )

            with gui.div(className="v2-about-byline-actions"):
                self._render_share_trigger(key="about-share")

    @staticmethod
    def _public_workflow_count(workspace: Workspace) -> int:
        """The same expression the public profile page counts with, so the two can never
        disagree. `VIEW_ONLY` is labelled "Private", so excluding it leaves the public ones.
        """
        return (
            PublishedRun.objects.filter(workspace=workspace)
            .exclude(public_access=WorkflowAccessLevel.VIEW_ONLY)
            .count()
        )

    def _render_about_meta(self):
        """Hook: a strip of cards summarising how this workflow is put together.

        What "put together" means is per-recipe - an agent has a model, a knowledge base and
        tools; a media-gen recipe has none of those - so the base renders nothing.
        """

    def _render_solo_input_col(self) -> bool:
        """The working column on its own, in the same row/column wrapper Split uses.

        Going through `gui.columns` rather than styling a bare div is what keeps Config's
        gutters, background and pane height identical to Split's: Bootstrap's grid supplies
        the padding and `SPLIT_PANES_CSS` the rest, so there is nothing to keep in sync by
        hand. One column of 12, instead of Split's 3-and-2.
        """
        with gui.styled(INPUT_OUTPUT_COLS_CSS + SPLIT_PANES_CSS):
            (input_col,) = gui.columns([1])
            with (
                input_col,
                # Centred and capped. With the whole row to itself this column would otherwise
                # run a form and a code editor edge to edge across a wide monitor, which is
                # both hard to read and unlike Split, where the preview caps it naturally.
                # `d-flex flex-column` + `minHeight: 0` because everything below depends on the
                # app shell's definite-height chain - a plain block here would break it.
                gui.div(
                    className="mx-auto w-100 h-100 d-flex flex-column",
                    style=dict(maxWidth=SOLO_COL_MAX_WIDTH, minHeight=0),
                ),
            ):
                return self._render_input_col()

    def _preview_frame(self):
        """Frames the preview when it shares the view with something else.

        Split and About put it next to a column of content, where a border separates the
        two. Preview is the whole view, so it needs no frame - a border there would just
        outline the viewport.
        """
        return gui.div(
            className="h-100",
            style=dict(
                border="1px solid #e0ddd7",
                borderRadius="12px",
                overflow="hidden",
                minHeight=0,
            ),
        )

    def _render_split_tab(self):
        """Both columns side by side - v1's Run tab.

        Unlike v1 this is *only* the two columns. v1 trailed the Debug expander, the usage
        guide and Related Workflows below the fold; in an app shell there is no page scroll
        to put them below, so the guide and Related Workflows live on About, and Debug
        becomes a Config sub-tab.
        """
        if self._render_deleted_output_if_needed():
            return

        with gui.styled(INPUT_OUTPUT_COLS_CSS + SPLIT_PANES_CSS):
            input_col, output_col = gui.columns([3, 2], gap="medium")
            with input_col:
                submitted = self._render_input_col()
            with output_col, self._preview_frame():
                self._render_output_col(submitted=submitted)

    def _render_deleted_output_if_needed(self) -> bool:
        """True if this run's data is gone, in which case that is all there is to render."""
        if self.current_sr.retention_policy != RetentionPolicy.delete:
            return False
        self.render_deleted_output()
        return True

    def render_selected_tab(self):
        """Bodies of the v1 tab urls the v2 strip drops - reached only by deep link."""
        match self.tab:
            case RecipeTabs.run | RecipeTabs.preview:
                self._render_split_tab()

            case RecipeTabs.examples:
                self._examples_tab()

            case RecipeTabs.history:
                self._history_tab()

            case RecipeTabs.run_as_api:
                self.run_as_api_tab()

            case RecipeTabs.saved:
                self._saved_tab()

    def _render_version_history(self):
        versions = self.current_pr.versions.all()
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
        url = self.app_url(
            example_id=version.published_run.published_run_id,
            run_id=version.saved_run.run_id,
            uid=version.saved_run.uid,
        )
        with gui.link(to=url, className="d-block text-decoration-none my-3"):
            with gui.div(
                className="d-flex justify-content-between align-items-middle fw-bold"
            ):
                if version.changed_by:
                    with gui.tag("h6"):
                        render_author_from_user(
                            version.changed_by, responsive=False, show_as_link=False
                        )
                else:
                    gui.write("###### Deleted User", className="container-margin-reset")
                with gui.tag("h6", className="mb-0"):
                    gui.html(
                        "Loading...",
                        **render_local_dt_attrs(
                            version.created_at,
                            date_options={"month": "short", "day": "numeric"},
                        ),
                    )
            with gui.div(className="container-margin-reset"):
                is_first_version = not older_version
                if is_first_version:
                    with gui.tag("span", className="badge bg-secondary px-3"):
                        gui.write("FIRST VERSION")
                elif version.change_notes:
                    gui.caption(
                        f"{icons.notes} {html.escape(version.change_notes)}",
                        unsafe_allow_html=True,
                    )
                elif older_version and older_version.title != version.title:
                    gui.caption(f"Renamed to: {version.title}")

    def render_related_workflows(self):
        page_clses = self.related_workflows()
        if not page_clses:
            return

        with gui.link(to="/explore/"):
            gui.html("<h2>Related Workflows</h2>")

        def _render(page_cls: typing.Type[BasePage]):
            page = page_cls()
            root_run = page.get_root_pr()
            preview_image = page.get_explore_image()

            with gui.link(to=page.app_url(), className="text-decoration-none"):
                gui.html(
                    # language=html
                    f"""
<div class="w-100 mb-2" style="height:150px; background-image: url({preview_image}); background-size:cover; background-position-x:center; background-position-y:30%; background-repeat:no-repeat;"></div>
                    """
                )
                gui.markdown(f"###### {root_run.title or page.title}")
                gui.caption(truncate_text_words(root_run.notes, maxlen=210))

        grid_layout(2, page_clses, _render)

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

            send_reported_run_email(
                user=self.request.user,
                run_uid=str(self.current_sr_user.uid),
                url=self.current_app_url(),
                recipe_name=self.title,
                report_type=report_type,
                reason_for_report=reason_for_report,
                error_msg=gui.session_state.get(StateKeys.error_msg),
            )

            if report_type == inappropriate_radio_text:
                self.update_flag_for_run(is_flagged=True)

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
                self.update_flag_for_run(is_flagged=False)
            gui.success("Removed flag.")
            sleep(2)
            gui.rerun()
        else:
            gui.write(
                "Our support team is reviewing this run. Please come back after some time."
            )
            # Return and Don't render the run any further
            gui.stop()

    def update_flag_for_run(self, is_flagged: bool):
        sr = self.current_sr
        sr.is_flagged = is_flagged
        sr.save(update_fields=["is_flagged", "updated_at"])
        gui.session_state["is_flagged"] = is_flagged

    def get_current_llm_tools(self) -> dict[str, BaseLLMTool]:
        return {
            tool.name: self.bind_tool(tool)
            for tool in itertools.chain(
                get_workflow_tools_from_state(
                    gui.session_state, FunctionTrigger.prompt
                ),
                get_inbuilt_tools(gui.session_state),
            )
        }

    def bind_tool(self, tool: BaseLLMTool) -> BaseLLMTool:
        match tool:
            case WorkflowLLMTool():
                return tool.bind(
                    saved_run=self.current_sr,
                    workspace=self.current_workspace,
                    current_user=self.request.user,
                    request_model=self.RequestModel,
                    response_model=self.ResponseModel,
                    state=gui.session_state,
                    trigger=FunctionTrigger.prompt,
                )
            case ComposioLLMTool():
                return tool.bind(
                    user_id=FunctionScopes.get_user_id_for_scope(
                        tool.scope,
                        workspace=self.current_workspace,
                        user=self.request.user,
                        published_run=self.current_pr,
                        variables=gui.session_state.get("variables"),
                    ),
                    redirect_url=self.current_app_url(
                        query_params={SUBMIT_AFTER_LOGIN_Q: "1"}
                    ),
                )
            case GooeyMemoryLLMTool():
                if not tool.scope:
                    tool.scope = FunctionScopes.workspace
                memory_entry = tool.scope.build_memory_entry(
                    saved_run=self.current_sr,
                    workspace=self.current_workspace,
                    user=self.request.user,
                    published_run=self.current_pr,
                    variables=gui.session_state.get("variables"),
                )
                return tool.bind(memory_entry)
            case _:
                return tool

    @cached_property
    def current_workspace(self) -> Workspace:
        if not self.request.user:
            raise Workspace.DoesNotExist(
                "User must be logged in to get their workspace"
            )
        return get_current_workspace(self.request.user, self.request.session)

    @cached_property
    def current_membership(self) -> WorkspaceMembership | None:
        if not self.request.user:
            return None

        return self.current_workspace.memberships.filter(
            user=self.request.user, deleted__isnull=True
        ).first()

    @cached_property
    def current_sr_user(self) -> AppUser | None:
        try:
            return self.current_sr.created_by
        except AppUser.DoesNotExist:
            return None

    @cached_property
    def current_sr(self) -> SavedRun:
        return self.current_sr_pr[0]

    @cached_property
    def current_pr(self) -> PublishedRun:
        return self.current_sr_pr[1]

    @cached_property
    def current_sr_pr(self) -> tuple[SavedRun, PublishedRun]:
        try:
            return self.get_sr_pr_from_query_params(
                *extract_query_params(self.request.query_params)
            )
        except (SavedRun.DoesNotExist, PublishedRun.DoesNotExist):
            raise HTTPException(status_code=404)

    @classmethod
    def get_sr_pr_from_query_params(
        cls, example_id: str, run_id: str, uid: str
    ) -> tuple[SavedRun, PublishedRun]:
        if example_id:
            example_pr = cls.get_pr_from_example_id(example_id)
        else:
            example_pr = None

        if run_id and uid:
            sr = cls.get_sr_from_ids(run_id=run_id, uid=uid)
            pr = example_pr or sr.parent_published_run() or cls.get_root_pr()
        else:
            pr = example_pr or cls.get_root_pr()
            sr = pr.saved_run

        return sr, pr

    @classmethod
    def get_sr_from_ids(
        cls,
        run_id: str,
        uid: str,
        *,
        create: bool = False,
        defaults: dict[str, typing.Any] | None = None,
    ) -> SavedRun:
        config = dict(workflow=cls.workflow, uid=uid, run_id=run_id)
        if create:
            return SavedRun.objects.get_or_create(**config, defaults=defaults)[0]
        else:
            return SavedRun.objects.select_related(
                "parent_version__published_run__saved_run__workflow_metadata",
                "parent_version__published_run__workspace",
                "workflow_metadata",
                "created_by",
            ).get(**config)

    @classmethod
    def get_pr_from_example_id(cls, example_id: str):
        return (
            PublishedRun.objects.select_related(
                "saved_run__workflow_metadata",
                "saved_run__created_by",
                "workspace",
                "created_by",
            )
            .prefetch_related("tags")
            .get(workflow=cls.workflow, published_run_id=example_id)
        )

    @classmethod
    def get_root_pr(cls) -> PublishedRun:
        return get_or_create_lazy(
            PublishedRun,
            workflow=cls.workflow,
            published_run_id="",
            create=lambda kwargs: PublishedRun.objects.create_with_version(
                **kwargs,
                saved_run=SavedRun.objects.get_or_create(
                    example_id="",
                    workflow=cls.workflow,
                    defaults=dict(state=cls.load_state_defaults({})),
                )[0],
                user=None,
                workspace=None,
                title=cls.title,
                public_access=WorkflowAccessLevel.FIND_AND_VIEW,
            ),
        )[0]

    @classmethod
    def create_published_run(
        cls,
        *,
        published_run_id: str,
        saved_run: SavedRun,
        user: AppUser | None,
        workspace: typing.Optional["Workspace"],
        title: str,
        notes: str,
        public_access: WorkflowAccessLevel | None = None,
        photo_url: str = "",
        tags: list[Tag] | None = None,
    ):
        return PublishedRun.objects.create_with_version(
            workflow=cls.workflow,
            published_run_id=published_run_id,
            saved_run=saved_run,
            user=user,
            workspace=workspace,
            title=title,
            notes=notes,
            public_access=public_access,
            photo_url=photo_url,
            tags=tags,
        )

    @classmethod
    def get_total_runs(cls) -> int:
        # TODO: fix to also handle published run case
        return SavedRun.objects.filter(workflow=cls.workflow).count()

    def render_settings(self):
        pass

    def render_is_cancelled(self):
        if not self.current_sr.is_cancelled:
            return
        if gui.session_state.get(StateKeys.run_status):
            cancel_msg = "We're trying our best to cancel this run, please be patient"
        else:
            cancel_msg = "Run was stopped. Results may be incomplete."
        gui.error(cancel_msg, icon="⚠️", color="#ffe8b2")

    def render_output(self):
        self.render_run_preview_output(gui.session_state)

    def render_form_v2(self):
        pass

    def validate_form_v2(self):
        pass

    def get_credits_click_url(self):
        if self.request.user and self.request.user.is_anonymous:
            return "/pricing/"
        else:
            return "/account/"

    def render_submit_row(self):
        gui.write("---")
        with gui.div(
            className="position-sticky bottom-0 container-margin-reset p-2",
            style=dict(
                background="rgba(249, 249, 249, 0.7)",
                backdropFilter="blur(7px)",
                WebkitBackdropFilter="blur(7px)",
                marginLeft="-0.5rem",
                marginRight="-0.5rem",
                zIndex=10,
            ),
        ):
            col1, col2 = gui.columns([2, 1], responsive=False)
            col2.node.props["className"] += (
                " d-flex justify-content-end align-items-center"
            )
            col1.node.props["className"] += " d-flex flex-column justify-content-center"
            with (
                col1,
                # make lineclamp button transparent
                gui.styled(
                    "& + span button { background-color: transparent !important; }"
                ),
            ):
                self.render_run_cost()
            with col2:
                return self.render_submit_button()

    def render_submit_button(self):
        if (
            gui.session_state.get(StateKeys.run_status)
            and not self.current_sr.is_cancelled
            and (self.is_current_user_owner() or self.is_current_user_admin())
        ):
            stopped = gui.button(
                f"{icons.cancel} Stop",
                key="-stop-workflow",
                className="my-0 py-2 text-danger",
            )
            if stopped:
                self.current_sr.is_cancelled = True
                self.current_sr.save(update_fields=["is_cancelled", "updated_at"])
                raise gui.RerunException
        else:
            submitted = gui.button(
                f"{icons.run} Run",
                key="-submit-workflow",
                type="primary",
                className="my-0 py-2",
            )
            if submitted:
                try:
                    self.validate_form_v2()
                    return True
                except AssertionError as e:
                    gui.error(str(e))
        return False

    # Number of lines to clamp the run cost notes to
    run_cost_line_clamp: int = 1

    def render_run_cost(self):
        gui.caption(
            self.get_run_cost_display(),
            line_clamp=self.run_cost_line_clamp,
            unsafe_allow_html=True,
        )

    def get_run_cost_display(self) -> str:
        url = self.get_credits_click_url()
        run_cost = self.get_run_cost_credits()
        if run_cost is not None:
            # dollars, not credits - the same readout the top bar shows, so the two places a
            # price appears on this page cannot disagree
            ret = (
                f'Run cost = <a href="{url}">{format_credits_as_dollars(run_cost)}</a>'
            )
        else:
            ret = ""

        cost_note = self.get_cost_note()
        if cost_note:
            ret += f" ({cost_note.strip()})"

        additional_notes = self.additional_notes()
        if additional_notes:
            ret += f" \n{additional_notes}"

        return ret

    def get_run_cost_credits(self) -> int | None:
        if self.current_sr.price and not self._has_request_changed():
            return self.current_sr.price
        elif self.price_deferred:
            return None
        else:
            return self.get_price_roundoff(gui.session_state)

    # v1's `_render_help` - the "How to Use This Recipe" guide plus the Discord embed - is
    # deliberately absent. About is the recipe's description, not its manual, and it was the
    # only v2 surface that rendered it. `render_usage_guide` stays: recipes still override it
    # and v1 still shows it.
    def render_usage_guide(self):
        raise NotImplementedError

    def main(self, sr: SavedRun, state: dict) -> typing.Iterator[str | None]:
        yield from self.ensure_credits_and_auto_recharge(state)

        yield from call_recipe_functions(
            saved_run=sr,
            workspace=self.current_workspace,
            current_user=self.request.user,
            request_model=self.RequestModel,
            response_model=self.ResponseModel,
            state=state,
            trigger=FunctionTrigger.pre,
        )

        yield from self.run(state)

        yield from call_recipe_functions(
            saved_run=sr,
            workspace=self.current_workspace,
            current_user=self.request.user,
            request_model=self.RequestModel,
            response_model=self.ResponseModel,
            state=state,
            trigger=FunctionTrigger.post,
        )

    def run(self, state: dict) -> typing.Iterator[str | None]:
        # initialize request and response
        request = self.RequestModel.model_validate(state)
        response = self.ResponseModel.model_construct()

        # run the recipe
        try:
            for val in self.run_v2(request, response):
                state.update(response.model_dump(exclude_unset=True))
                yield val
        finally:
            state.update(response.model_dump(exclude_unset=True))

        # validate the response if successful
        self.ResponseModel.model_validate(response)

    def run_v2(
        self, request: RequestModel, response: BaseModel
    ) -> typing.Iterator[str | None]:
        raise NotImplementedError

    def _render_report_button(self):
        sr, pr = self.current_sr_pr
        is_example = pr.saved_run_id == sr.id
        # only logged in users can report a run (but not examples/root runs)
        if not self.request.user or is_example:
            return

        with gui.tooltip("Report"):
            reported = gui.button(
                icons.flag,
                type="tertiary",
                className="mb-0 p-1",
            )
        if not reported:
            return

        gui.session_state["show_report_workflow"] = reported
        gui.rerun()

    # Functions in every recipe feels like overkill for now, hide it in settings
    functions_in_settings = True
    show_settings = True

    def _render_input_col(self):
        if self.tab == RecipeTabs.preview:
            hide_on_mobile = "d-none d-lg-block"
        else:
            hide_on_mobile = ""
        with gui.div(className=hide_on_mobile):
            self.render_form_v2()
            placeholder = gui.div()

            if self.show_settings:
                with gui.div(className="bg-white mt-2"), gui.expander("⚙️ Settings"):
                    self.render_settings()
                    if self.functions_in_settings:
                        functions_input(
                            workspace=self.request.user and self.current_workspace,
                            user=self.request.user,
                            published_run=self.current_pr,
                        )

            with placeholder:
                self.render_variables()

            submitted = self.render_submit_row()
            with gui.div(style={"textAlign": "right", "fontSize": "smaller"}):
                terms_caption = self.get_terms_caption()
                gui.caption(f"_{terms_caption}_")

            return submitted

    def get_terms_caption(self):
        return "With each run, you agree to Gooey.AI's [terms](https://gooey.ai/terms) & [privacy policy](https://gooey.ai/privacy)."

    def render_variables(self):
        """v1's combined block, kept whole for the default input column.

        A recipe that wants them apart uses the two halves directly - VideoBots keeps
        functions on the Tools pane and opens the variables editor in a dialog beside the
        prompt, which is where the variables are actually referenced.
        """
        self._render_functions()
        self._render_variables_editor()

    def _render_functions(self):
        if not self.functions_in_settings:
            functions_input(
                workspace=self.request.user and self.current_workspace,
                user=self.request.user,
                published_run=self.current_pr,
            )

    def _variable_exclusions(self) -> list[str]:
        """Names the variables editor must not offer: the request/response fields, and the
        function slugs, which have inputs of their own.

        Shared with `variable_names()` so the count beside the prompt cannot disagree with
        what the editor actually lists.
        """
        function_slugs = [
            slug
            for fn in gui.session_state.get("functions", [])
            if (slug := fn.get("slug"))
        ]
        return self.fields_to_save() + function_slugs

    def _render_variables_editor(self, *, heading: bool = True):
        """`heading=False` where the surface already names itself - the dialog's own title.

        Emptying the label also drops the help tooltip beside it: `variables_input` always
        passes a `help=` string, but `RenderedMarkdown` returns nothing at all for an empty
        body, so the icon never gets built. The dialog's intro says the same thing in full,
        Learn more link included.
        """
        variables_input(
            template_keys=self.template_keys,
            # v1 gated Add on `is_functions_enabled()` - the switch inside `functions_input`,
            # which in v1 sits directly above this editor, so the gate is at least visible.
            # v2 puts functions on the Tools pane and variables in a dialog, so there it
            # reads as nothing but a missing button. Adding a variable needs no function
            # either way: the prompt is what consumes them.
            allow_add=True,
            exclude=self._variable_exclusions(),
            **({} if heading else dict(label="")),
        )

    def variable_names(self) -> set[str]:
        """The variables the editor would list, for a count shown before it renders.

        Mirrors `variables_input`'s own set arithmetic: whatever the prompt references plus
        whatever has been set explicitly, less the jinja globals and the exclusions. Derived
        from `template_keys` rather than from the editor's session-state list, so the count
        is right even when the editor has never been opened.
        """
        from daras_ai_v2.variables_widget import context_globals, find_template_vars

        _, template_var_names = find_template_vars(self.template_keys)
        explicit = gui.session_state.get("variables") or {}
        return (
            (template_var_names | set(explicit))
            - set(context_globals())
            - set(self._variable_exclusions())
        )

    @classmethod
    def get_run_state(cls, state: dict[str, typing.Any]) -> RecipeRunState:
        if detail := state.get(StateKeys.run_status):
            if detail.lower().strip(". ") == STARTING_STATE.lower().strip(". "):
                return RecipeRunState.starting
            else:
                return RecipeRunState.running
        elif state.get(StateKeys.error_msg):
            return RecipeRunState.failed
        elif state.get(StateKeys.run_time):
            return RecipeRunState.completed
        else:
            return RecipeRunState.standby

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

        if submitted:
            self.submit_and_redirect()

        # h-100 so a percentage-height child (the chat widget) resolves against the
        # scrolling body area rather than the viewport
        with gui.div(
            style=dict(height="100%", minHeight=0),
            className=self._output_col_class_name(),
        ):
            run_state = self.get_run_state(gui.session_state)
            if run_state == RecipeRunState.failed:
                self._render_failed_output()

            # render outputs
            if not is_deleted:
                self.render_is_cancelled()
                self.render_output()

            if run_state in (RecipeRunState.running, RecipeRunState.starting):
                self.click_preview_tab()
                self._render_running_output()
            elif not is_deleted:
                self._render_after_output()

    def _output_col_class_name(self) -> str:
        """The client-side Preview view controls visibility at every breakpoint."""
        return ""

    def _render_failed_output(self):
        if not self._render_custom_error():
            err_msg = gui.session_state.get(StateKeys.error_msg)
            gui.error(err_msg, unsafe_allow_html=True)

    def _render_custom_error(self) -> bool:
        if not self.current_sr or not self.current_sr.error_type:
            return False
        render = exceptions.get_error_renderer(self.current_sr.error_type)
        if not render:
            return False
        error_params = dict(self.current_sr.error_params or {})
        error_params.update(self._get_default_error_params())
        render(error_params)
        return True

    def _get_default_error_params(self) -> dict[str, typing.Any]:
        ret = {"request": self.request, "sr": self.current_sr}
        if self.request.user:
            ret.update({"current_workspace": self.current_workspace})
        return ret

    def click_preview_tab(self):
        # show the preview tab when running
        gui.html(
            """
            <script>
            window.addEventListener("hydrated", function() {
                document.getElementById("tabs--tab--0")?.click();
            });
            </script>
            """
        )

    scroll_into_view = True

    def _render_running_output(self):
        run_status = gui.session_state.get(StateKeys.run_status)
        html_spinner(run_status, scroll_into_view=self.scroll_into_view)
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

    def submit_and_redirect(
        self,
        unsaved_state: dict[str, typing.Any] | None = None,
        **defaults,
    ):
        sr = self.on_submit(unsaved_state=unsaved_state, **defaults)
        if not sr:
            return

        raise gui.RedirectException(self.app_url(run_id=sr.run_id, uid=sr.uid))

    def publish_and_redirect(self) -> typing.NoReturn | None:
        assert self.is_logged_in()

        updated_count = SavedRun.objects.filter(
            id=self.current_sr.id,
            # filter for RecipeRunState.standby
            run_status="",
            error_msg="",
            run_time=datetime.timedelta(),
        ).update(run_status=STARTING_STATE, uid=self.request.user.uid)
        if updated_count >= 1:
            # updated now
            self.current_sr.refresh_from_db()
            self.call_runner_task(self.current_sr)

        pr = self.create_published_run(
            published_run_id=get_random_doc_id(),
            saved_run=self.current_sr,
            user=self.request.user,
            workspace=self.current_workspace,
            title=self._get_default_pr_title(),
            notes=self.current_pr.notes,
            tags=list(self.current_pr.tags.all()),
        )
        raise gui.RedirectException(pr.get_app_url())

    def on_submit(
        self,
        unsaved_state: dict[str, typing.Any] | None = None,
        **defaults,
    ):
        sr = self.create_and_validate_new_run(enable_rate_limits=True, **defaults)
        if not sr:
            return
        self.call_runner_task(sr, unsaved_state=unsaved_state)
        return sr

    def should_submit_after_login(self) -> bool:
        should_submit = bool(self.request.query_params.get(SUBMIT_AFTER_LOGIN_Q))

        if should_submit:
            # if the user is already logged in, then submit the run, otherwise ignore this flag
            return self.is_logged_in()

        # if the user is not logged in and the error is due to insufficient credits,
        # then flag to submit the run after the user logs in
        if (
            self.current_sr.error_type == exceptions.InsufficientCredits.__name__
            and not self.is_logged_in()
        ):
            self.request.query_params[SUBMIT_AFTER_LOGIN_Q] = "1"
            raise gui.QueryParamsRedirectException(self.request.query_params)

    def should_publish_after_login(self) -> bool:
        return bool(
            self.request.query_params.get(PUBLISH_AFTER_LOGIN_Q) and self.is_logged_in()
        )

    def create_and_validate_new_run(
        self,
        *,
        enable_rate_limits: bool = False,
        run_status: str | None = STARTING_STATE,
        **defaults,
    ) -> SavedRun | None:
        try:
            sr = self.create_new_run(
                enable_rate_limits=enable_rate_limits, run_status=run_status, **defaults
            )
        except ValidationError as e:
            traceback.print_exc()
            gui.session_state[StateKeys.run_status] = None
            gui.session_state[StateKeys.error_msg] = str(e)
            return
        except RateLimitExceeded as e:
            gui.session_state[StateKeys.run_status] = None
            gui.session_state[StateKeys.error_msg] = e.detail.get("error", "")
            return
        return sr

    def create_new_run(
        self,
        *,
        enable_rate_limits: bool = False,
        run_status: str | None = STARTING_STATE,
        **defaults,
    ) -> SavedRun:
        from routers.firebase_auth import init_firebase_anonymous_user

        gui.session_state[StateKeys.run_status] = run_status
        gui.session_state.pop(StateKeys.error_msg, None)
        gui.session_state.pop(StateKeys.run_time, None)
        self._setup_rng_seed()
        self.clear_outputs()

        assert self.request, "request is not set for current session"
        if not self.request.user:
            init_firebase_anonymous_user(self.request)

        if enable_rate_limits:
            ensure_rate_limits(self.workflow, self.request.user, self.current_workspace)

        run_id = get_random_doc_id()

        parent, pr = self.current_sr_pr
        try:
            parent_version = pr.versions.latest()
        except PublishedRunVersion.DoesNotExist:
            parent_version = None

        defaults = (
            dict(
                parent=parent,
                parent_version=parent_version,
                workspace=self.current_workspace,
                parent_builder_saved_run=parent.parent_builder_saved_run,
            )
            | defaults
        )
        sr = self.get_sr_from_ids(
            run_id, self.request.user.uid, create=True, defaults=defaults
        )

        self.dump_state_to_sr(self._get_validated_state(), sr)

        return sr

    def _get_validated_state(self) -> dict:
        # ensure the request is validated
        return gui.session_state | json.loads(
            self.RequestModel.model_validate(gui.session_state).model_dump_json(
                exclude_unset=True
            )
        )

    def dump_state_to_sr(self, state: dict, sr: SavedRun):
        sr.set(
            {
                field_name: deepcopy(state[field_name])
                for field_name in self.fields_to_save()
                if field_name in state
            }
        )

    def call_runner_task(
        self,
        sr: SavedRun,
        deduct_credits: bool = True,
        unsaved_state: dict[str, typing.Any] = None,
    ):
        from celeryapp.tasks import runner_task

        result = runner_task.delay(
            page_cls=self.get_runner_page_cls(),
            user_id=self.request.user.id,
            run_id=sr.run_id,
            uid=sr.uid,
            channel=self.realtime_channel_name(sr.run_id, sr.uid),
            unsaved_state=unsaved_state,
            deduct_credits=deduct_credits,
        )
        # persist task id so a Stop click can revoke it mid-run
        sr.celery_task_id = result.id
        sr.save(update_fields=["celery_task_id", "updated_at"])
        return result

    @classmethod
    def get_runner_page_cls(cls):
        """The stable page class serialized into Celery jobs."""
        return cls

    @classmethod
    def realtime_channel_name(cls, run_id: str, uid: str) -> str:
        return f"gooey-outputs/{cls.canonical_slug()}/{uid}/{run_id}"

    def _setup_rng_seed(self):
        seed = gui.session_state.get("seed")
        if not seed:
            return
        gooey_rng.seed(seed)

    def clear_outputs(self):
        # clear error msg
        gui.session_state.pop(StateKeys.error_msg, None)
        # clear outputs
        for field_name in self.ResponseModel.model_fields:
            gui.session_state.pop(field_name, None)

    def _render_after_output(self):
        self._render_regenerate_button()

    def _render_regenerate_button(self):
        if "seed" in self.RequestModel.schema_json():
            randomize = gui.button(f"{icons.regenerate} Regenerate", type="tertiary")
            if randomize:
                gui.session_state[StateKeys.pressed_randomize] = True
                gui.rerun()

    def current_sr_to_session_state(self) -> dict:
        state = self.current_sr.to_dict()
        if state is None:
            raise HTTPException(status_code=404)
        return self.load_state_defaults(state)

    @classmethod
    def load_state_defaults(cls, state: dict):
        for field_name, properties in cls.RequestModel.model_json_schema()[
            "properties"
        ].items():
            default_val = properties.get("default")
            if default_val is None:
                continue
            try:
                state.setdefault(field_name, copy(default_val))
            except KeyError:
                pass
        for field_name, default_val in cls.sane_defaults.items():
            state.setdefault(field_name, default_val)
        return state

    def fields_to_save(self) -> list[str]:
        # only save the fields in request/response
        return [
            field_name
            for model in (self.RequestModel, self.ResponseModel)
            for field_name in model.model_fields
        ] + [
            StateKeys.error_msg,
            StateKeys.run_status,
            StateKeys.run_time,
        ]

    def _examples_tab(self):
        qs = (
            PublishedRun.objects.select_related(
                "saved_run", "workspace", "last_edited_by"
            )
            .prefetch_related("tags", "versions")
            .filter(PublishedRun.approved_example_q(), workflow=self.workflow)
        )

        example_runs, cursor = paginate_queryset(
            qs=qs,
            ordering=["-example_priority", "-updated_at"],
            cursor=self.request.query_params,
        )

        def _render(pr: PublishedRun):
            render_saved_workflow_preview(
                pr,
                show_workspace_author=True,
                hide_access_level=True,
                hide_version_notes=True,
            )

        grid_layout(1, example_runs, _render)

        paginate_button(url=self.request.url, cursor=cursor)

    def _saved_tab(self):
        self.ensure_authentication()

        pr_filter = Q(workspace=self.current_workspace)
        if self.current_workspace.is_personal:
            pr_filter |= Q(created_by=self.request.user, workspace__isnull=True)
        else:
            pr_filter &= (
                ~Q(workspace_access=WorkflowAccessLevel.VIEW_ONLY)
                | Q(created_by=self.request.user)
                | ~Q(public_access=WorkflowAccessLevel.VIEW_ONLY)
            )

        qs = (
            PublishedRun.objects.select_related(
                "saved_run", "workspace", "last_edited_by"
            )
            .prefetch_related("tags", "versions")
            .filter(pr_filter, workflow=self.workflow)
        )

        published_runs, cursor = paginate_queryset(
            qs=qs, ordering=["-updated_at"], cursor=self.request.query_params
        )

        if not published_runs:
            gui.write("No published runs yet")
            return

        with gui.div(className="position-relative w-100"):
            grid_layout(1, published_runs, render_saved_workflow_preview)

        paginate_button(url=self.request.url, cursor=cursor)

    def _history_tab(self):
        self.ensure_authentication(anon_ok=True)

        # Filter by workspace
        qs = SavedRun.objects.filter(
            workflow=self.workflow, workspace=self.current_workspace
        )

        if not self.is_current_user_admin():
            qs = qs.exclude(surface=SavedRun.Surface.builder_prompt)

        # Apply user filter if specified
        for_param = self.request.query_params.get("for", "me")
        if (
            for_param != "all"
            and self.request.user
            and not self.current_workspace.is_personal
        ):
            qs = qs.filter(uid=self.request.user.uid).exclude(
                surface=SavedRun.Surface.deployment
            )

        run_history, cursor = paginate_queryset(
            qs=qs, ordering=["-updated_at"], cursor=self.request.query_params
        )
        if not run_history:
            gui.write("No history yet")
            return

        grid_layout(3, run_history, self._render_run_preview)

        paginate_button(url=self.request.url, cursor=cursor)

    def ensure_authentication(self, next_url: str | None = None, anon_ok: bool = False):
        if not self.request.user or (self.request.user.is_anonymous and not anon_ok):
            raise gui.RedirectException(self.get_auth_url(next_url))

    def is_logged_in(self) -> bool:
        return bool(self.request.user and not self.request.user.is_anonymous)

    def get_auth_url(self, next_url: str | None = None) -> str:
        return get_login_url(self.request, next_url)

    def _render_run_preview(self, saved_run: SavedRun):
        from daras_ai_v2.billing import left_and_right

        published_run: PublishedRun | None = (
            saved_run.parent_version.published_run if saved_run.parent_version else None
        )
        is_latest_version = published_run and published_run.saved_run == saved_run
        tb = get_title_breadcrumbs(self, sr=saved_run, pr=published_run)

        with gui.link(
            to=saved_run.get_app_url(), className="text-decoration-none text-reset"
        ):
            with gui.div(className="mb-1", style={"fontSize": "0.9rem"}):
                if is_latest_version:
                    gui.pill(
                        published_run.get_share_badge_html(),
                        unsafe_allow_html=True,
                        className="border border-dark",
                    )
            gui.write(f"#### {tb.title_with_prefix()}")

            author, _ = AppUser.objects.get_or_create_from_uid(saved_run.uid)
            updated_at = saved_run.updated_at
            left, right = left_and_right(className="container-margin-reset")
            with left:
                render_author_from_user(author)
            with right:
                if (
                    updated_at
                    and isinstance(updated_at, datetime.datetime)
                    and not saved_run.run_status
                ):
                    gui.caption(
                        f"{icons.time} {get_relative_time(updated_at)}",
                        unsafe_allow_html=True,
                    )

            with gui.div(className="mt-2"):
                if saved_run.run_status:
                    started_at_text(saved_run.created_at)
                    html_spinner(saved_run.run_status)
                elif saved_run.error_msg:
                    gui.error(saved_run.error_msg, unsafe_allow_html=True)
                else:
                    self.render_run_preview_output(saved_run.to_dict())

    def render_run_preview_output(self, state: dict):
        pass

    def render_steps(self):
        pass

    @classmethod
    def preview_input(cls, state: dict) -> str | None:
        return (
            state.get("text_prompt")
            or state.get("input_prompt")
            or state.get("search_query")
            or state.get("title")
        )

    @classmethod
    def preview_output(cls, state: dict) -> str | None:
        out = (
            state.get("cutout_image")
            or state.get("output_images")
            or state.get("output_image")
            or state.get("output_video")
            or state.get("output_videos")
        )
        return extract_nested_str(out)

    def run_as_api_tab(self):
        api_docs_url = str(
            furl(
                settings.API_BASE_URL,
                fragment_path=f"operation/{self.canonical_slug()}",
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

        api_url, request_body = self.get_example_request(
            self.current_sr.state,
            include_all=include_all,
            pr=self.current_pr,
        )
        response_body = self.get_example_response_body(
            self.current_sr.state, as_async=as_async, include_all=include_all
        )

        api_example_generator(
            api_url=api_url,
            request_body=request_body,
            as_form_data=as_form_data,
            as_async=as_async,
        )
        gui.write("")

        gui.write("#### 🎁 Example Response")
        gui.json(response_body, expanded=True)

        if not self.is_logged_in():
            gui.write("**Please Login to generate the `$GOOEY_API_KEY`**")
            return

        gui.write("---")
        with gui.tag("a", id="api-keys"):
            gui.write("### 🔐 API keys")

        manage_api_keys(workspace=self.current_workspace, user=self.request.user)

    def ensure_credits_and_auto_recharge(self, state: dict):
        if not settings.CREDITS_TO_DEDUCT_PER_RUN:
            return
        assert self.request.user, "request.user must be set to check credits"

        workspace = self.current_workspace
        price = self.get_price_roundoff(state)

        if PricingPlan.from_sub(workspace.subscription) == PricingPlan.TEAM:
            membership = self.current_membership
            if not membership:
                raise exceptions.UserError("""
                  The workspace member who created this workflow is no longer part of the workspace.
                """)
            if membership.balance >= price:
                return
            raise exceptions.InsufficientCredits(price=price)

        if workspace.balance >= price:
            return

        if should_attempt_auto_recharge(workspace):
            yield "Low balance detected. Recharging..."
            run_auto_recharge_gracefully(workspace)
            workspace.refresh_from_db()

        if workspace.balance >= price:
            return

        raise exceptions.InsufficientCredits(price=price)

    def deduct_credits(self, state: dict) -> tuple[AppUserTransaction, int]:
        assert self.request.user, "request.user must be set to deduct credits"

        amount = self.get_price_roundoff(state)
        invoice_id = f"gooey_in_{uuid.uuid1()}"

        if (
            PricingPlan.from_sub(self.current_workspace.subscription)
            == PricingPlan.TEAM
        ):
            if self.current_membership:
                txn = self.current_membership.add_balance(
                    amount=-amount, invoice_id=invoice_id
                )
                return txn, amount

        txn = self.current_workspace.add_balance(
            amount=-amount,
            user=self.request.user,
            invoice_id=invoice_id,
        )
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
        sr = self.current_sr
        total = sr.usage_costs.aggregate(total=Sum("dollar_amount"))["total"]
        if not total:
            return default
        return total * settings.ADDON_CREDITS_PER_DOLLAR

    def get_grouped_linked_usage_cost_in_credits(self):
        """Return the linked usage costs grouped by model name in gooey credits."""
        qs = self.current_sr.usage_costs.values("pricing__model_name").annotate(
            total=Sum("dollar_amount") * settings.ADDON_CREDITS_PER_DOLLAR
        )
        return {item["pricing__model_name"]: item["total"] for item in qs}

    @classmethod
    def get_example_preferred_fields(cls, state: dict) -> list[str]:
        """
        Fields that are not required, but are preferred to be shown in the example.
        """
        return []

    @classmethod
    def get_tool_call_schema(cls, state: dict) -> dict[str, typing.Any]:
        """Return top-level request properties for tool calling schema."""
        properties = get_full_pydantic_schema(cls.RequestModel)
        patch_ai_model_schema_enums(properties)
        return properties

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
        sr = self.current_sr
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
        """Return additional notes to display. Override in subclasses."""
        pass

    def get_cost_note(self) -> str | None:
        pass

    def is_current_user_admin(self) -> bool:
        return self.is_user_admin(self.request.user)

    @classmethod
    def is_user_admin(cls, user: AppUser | None) -> bool:
        return bool(user and user.is_admin())

    def is_current_user_paying(self) -> bool:
        try:
            return self.current_workspace.is_paying
        except Workspace.DoesNotExist:
            return False

    def is_current_user_owner(self) -> bool:
        return bool(self.request.user and self.current_sr_user == self.request.user)

    def is_user_authorized(self, user: AppUser | None = None) -> bool:
        if self.is_user_admin(user):
            return True
        sr, pr = self.current_sr_pr
        # saved workflow pages
        if pr.saved_run_id == sr.id:
            workspace = pr.workspace
            # approved examples can be accessed by anyone
            if pr.is_approved_example:
                return True
            # saved workflow explicitly set to public access
            if pr.public_access >= WorkflowAccessLevel.FIND_AND_VIEW:
                return True
        # workflow run pages
        else:
            workspace = sr.workspace
            # runs created in free tier workspaces are public
            if not (workspace and workspace.subscription_id):
                return True
            if PricingPlan.from_sub(workspace.subscription) == PricingPlan.STARTER:
                return True
            # workspace explicitly set to be public_by_default
            if workspace.should_default_runs_be_public():
                return True
        # members can access
        return bool(user and workspace in user.cached_workspaces)


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


def extract_model_fields(
    model: typing.Type[BaseModel],
    state: dict,
    include_all: bool = True,
    preferred_fields: typing.Iterable[str] | None = None,
    unpreferred_fields: typing.Iterable[str] = ("variables_schema",),
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
        for field_name, field_info in model.model_fields.items()
        if (
            include_all
            or field_info.is_required()
            or (preferred_fields and field_name in preferred_fields)
            or (diff_from and state.get(field_name) != diff_from.get(field_name))
        )
        and field_name not in unpreferred_fields
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


FILL_HEIGHT_EDITOR_CSS = """
/* A code editor that fills its flex parent instead of sizing to its content.

   Every element in this chain has to be told to grow, or the height stops there. The
   widget is CodeMirror, not Ace, and react-codemirror inserts a `.cm-theme` wrapper that
   is easy to miss:

     &  ->  .code-editor-wrapper  ->  .cm-theme  ->  .cm-editor  ->  .cm-scroller

   `gui.styled` does not add a node - it merges its class onto its children - so `&` is the
   flex column this is used inside. `CodeEditor` also destructures `height` out of its props
   without forwarding it, so CSS is the only way to size this. */
& {
    min-height: 0;
}

& .code-editor-wrapper,
& .cm-theme {
    display: flex;
    flex-direction: column;
    flex: 1 1 auto;
    min-height: 0;
}

& .cm-editor {
    flex: 1 1 auto;
    min-height: 0;
    /* 10px to match the model selector directly above it and the pane pills above that -
       they read as one group, so they should share a corner. `overflow: hidden` because the
       line-number gutter and the scroller both paint to the editor's edge; without it their
       square corners show through the rounded ones. */
    border-radius: 10px;
    overflow: hidden;
}

/* the editor's own scroller owns the overflow, so the panes above it do not */
& .cm-scroller {
    overflow: auto;
}

/* Below lg the columns stack, so there is no fixed-height chain to grow into and the
   editor would collapse to its content. Give it a viewport-relative floor instead. */
@media (max-width: 991.98px) {
    & .cm-editor {
        min-height: 55vh;
    }
}
"""

PANE_STRIP_CSS = """
/* The strip spans the column and scrolls sideways when the pills do not fit, rather than
   wrapping onto a second row - a two-row strip pushes the pane down and reflows the whole
   column every time the window changes width.

   `!important` throughout: these compete with the app's own button styling, which is more
   specific than a scoped `& button` rule and otherwise wins (tertiary buttons come with
   their own padding and a pink hover). */
& {
    display: flex;
    flex-wrap: nowrap;
    gap: 8px;
    width: 100%;
    flex-shrink: 0;
    overflow-x: auto;
    overflow-y: hidden;
    scrollbar-width: thin;
    /* A rule under the strip, separating it from the pane it switches. The padding is what
       keeps the line off the pills - and it doubles as room for the active pill's shadow,
       which `overflow-y: hidden` was clipping. */
    padding-bottom: 12px;
    border-bottom: 1px solid #e6e6e6;
}

& button {
    flex: 0 0 auto;
    /* inline-flex keeps the active dot on the same line as the label; with inline-block it
       becomes a block-level box and the label drops to a second line */
    display: inline-flex !important;
    align-items: center;
    white-space: nowrap !important;
    margin: 0 !important;
    padding: 6px 14px !important;
    border: 1px solid #e6e6e6 !important;
    border-radius: 10px !important;
    background: #fff !important;
    color: #6b6b6b !important;
    font-weight: 500 !important;
    line-height: 1.4 !important;
    font-size: 0.875rem !important;
}

& button:hover {
    background: #fff !important;
    border-color: #d0d0d0 !important;
    color: #1a1a1a !important;
}

& button.pane-active {
    border-color: #c9c9c9 !important;
    color: #111 !important;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

& button.pane-active::before {
    content: "";
    flex: 0 0 auto;
    width: 6px;
    height: 6px;
    margin-right: 8px;
    border-radius: 50%;
    background: #111;
}
"""

SPLIT_PANES_CSS = """
/* App-shell panes, desktop only. The row fills the body exactly, so the body never
   overflows and therefore never scrolls; the left pane scrolls inside itself and the right
   pane (the preview) stays put.

   Below lg the columns stack (col-12), so this is deliberately not applied - there the row
   grows and the body scrolls normally, which is the right behaviour on a phone. */
& {
    margin: 0;
    padding-top: 0;
}

@media (min-width: 992px) {
    & {
        height: 100%;
        min-height: 0;
    }
    & > div {
        height: 100%;
        min-height: 0;
        /* the working column starts at the page's own padding, with no gutter on top of it -
           on the row's children, because a wrapper div around `with input_col:` would mount
           beside the row, not around the columns */
        padding-left: 0px;
    }
    /* Neither column scrolls as a whole. The left column is a flex stack whose *pane*
       scrolls, so its strip and submit row stay put; the right column is the preview,
       which manages its own scrolling. */
    & > div {
        overflow: hidden;
    }
    /* The preview sits flush against the page's right edge: it is a framed surface of its
       own, so a gutter between the frame and the edge just wastes width the chat could use.
       `:not(:first-child)` keeps this to the *second* of two columns - on Config the single
       working column is both first and last, and it keeps its gutter. */
    & > div:last-child:not(:first-child) {
        padding-right: 0;
    }
}
"""

INPUT_OUTPUT_COLS_CSS = """
& {
    margin: -1rem 0 1rem 0;
    padding-top: 1rem;
}

/* reset col padding in mobile */
& > div {
    padding: 0; 
}

@media (min-width: 768px) {
    & {
        background-color: #FBFAF8;
    }
    /* set col padding in mobile */
    & > div {
        padding-left: calc(var(--bs-gutter-x) * .5);
        padding-right: calc(var(--bs-gutter-x) * .5);
    }
}
"""

# The About tab: one card holding the title, who published it, the description, a strip of
# "how it is put together" cards, and the usage guide last. `!important` on the buttons for
# the same reason PANE_STRIP_CSS needs it - the app's own button styling is more specific
# than a scoped `& button` rule.
# The variables editor, shown in a dialog rather than on a pane of its own.
VARIABLES_DIALOG_CSS = """
/* `.modal-header` and `.modal-body` each bring a rem of padding, and the h4 title its own
   margin, so three lots of spacing stack up between the title and the first line. Pulled
   back here rather than restyled on the modal itself - every other dialog wants that
   spacing. */
& {
    margin-top: -0.75rem;
}

/* `variables_input` wraps itself in a grey card, which earns its keep on a crowded pane but
   not in a dialog - the dialog *is* the card. With no variables to list it has nothing in it
   either, and renders as an empty grey bar. */
& .bg-light {
    background: transparent !important;
    margin: 0 !important;
    padding: 0 !important;
}
"""

ABOUT_CSS = """
/* Above lg SPLIT_PANES_CSS makes every column `height: 100%; overflow: hidden`, so nothing
   here scrolls unless this does - a description longer than the viewport is simply clipped.
   Split needs no equivalent because its working column has an `overflow-auto` pane inside;
   About is one card, so the card's container is what has to scroll. */
@media (min-width: 992px) {
    & {
        height: 100%;
        min-height: 0;
        overflow-y: auto;
        /* keeps the scrollbar off the card's border instead of on top of it */
        padding-right: 0.5rem;
    }
}

& .v2-about-card {
    background: #fff;
    border: 1px solid #e0ddd7;
    border-radius: 12px;
    padding: 1.25rem;
}

/* Leads the card. A banner by default; `CIRCLE_IMAGE_WORKFLOWS` gets a portrait instead,
   which is the shape an agent's avatar is drawn for. */
/* The card's header: avatar on one side, title and byline stacked beside it. */
& .v2-about-head {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1.25rem;
}

/* takes the rest of the row, so the byline's `margin-left: auto` still puts Share against
   the card's right edge rather than against the title's */
& .v2-about-headtext {
    flex: 1 1 auto;
    min-width: 0;
}

& .v2-about-photo {
    display: block;
    width: 72px;
    height: 72px;
    object-fit: cover;
    border-radius: 12px;
    flex-shrink: 0;
}

& .v2-about-photo-circle {
    border-radius: 50%;
}

& .v2-about-title {
    font-size: 1.6rem;
    font-weight: 600;
    line-height: 1.3;
    /* the byline sits directly under it inside the same column */
    margin: 0 0 0.25rem 0;
}

& .v2-about-byline {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-wrap: wrap;
}

/* a secondary line under the title now, not a block of its own - so the author's mark stays
   well under the workflow avatar it sits beside */
& .v2-about-byline-photo {
    width: 24px;
    height: 24px;
    border-radius: 6px;
    object-fit: cover;
    flex-shrink: 0;
}

& .v2-about-byline-name {
    font-weight: 600;
    font-size: 0.875rem;
    line-height: 1.2;
}

& .v2-about-byline-sub {
    color: #6b6b6b;
    font-size: 0.8125rem;
}

/* pushed to the far end of the row, so it stays put however long the name is */
& .v2-about-byline-actions {
    margin-left: auto;
}

& .v2-about-notes {
    color: #333;
    margin-bottom: 1.5rem;
}

& .v2-about-section-title {
    /* a quiet label over the cards, not a heading competing with the title */
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: #8a8578;
    margin: 0 0 0.625rem 0;
}

/* Cards keep one fixed width and wrap. They are chips summarising a setting, not table rows:
   stretching them to fill the row leaves a card with three words in it spanning the pane, and
   a set of two looks broken next to a set of three. Fixed width also means the row reflows
   identically whether the Builder is open beside it or not. */
& .v2-about-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.625rem;
}

& .v2-about-meta-card {
    display: flex;
    align-items: center;
    gap: 0.625rem;
    /* 13rem, never wider: `0` grow so a long model name cannot stretch it, `1` shrink so a
       pane narrower than one card (Builder open, or a phone) makes it smaller rather than
       overflowing sideways */
    flex: 0 1 13rem;
    max-width: 13rem;
    padding: 0.75rem;
    border: 1px solid #ebe8e2;
    border-radius: 12px;
    background: #fff;
    color: #111;
    text-decoration: none;
    transition: border-color 0.12s ease, box-shadow 0.12s ease;
}

& .v2-about-meta-card:hover {
    border-color: #d6d1c7;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
    color: #111;
}

/* the icon gets its own tinted chip so a monochrome FontAwesome glyph and a model
   creator's colour logo both sit on the same footprint */
& .v2-about-meta-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 2rem;
    height: 2rem;
    border-radius: 8px;
    background: #f6f4f0;
    font-size: 0.9375rem;
    line-height: 1;
    color: #5f5a4e;
    flex-shrink: 0;
}

& .v2-about-meta-icon img {
    height: 1.125rem;
    width: 1.125rem;
    object-fit: contain;
}

& .v2-about-meta-label {
    flex: 1 1 auto;
    min-width: 0;
    font-size: 0.875rem;
    font-weight: 500;
    line-height: 1.3;
    /* a long model name ellipsises instead of wrapping the card to two lines and breaking
       the grid's even row height */
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

& .v2-about-meta-chevron {
    font-size: 0.75rem;
    color: #b5b0a6;
    flex-shrink: 0;
}

& .v2-about-meta-card:hover .v2-about-meta-chevron {
    color: #6b6b6b;
}
"""
