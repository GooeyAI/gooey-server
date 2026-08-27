import html
import inspect
import typing
from textwrap import dedent

import gooey_gui as gui
from bots.models import (
    PublishedRun,
    RetentionPolicy,
    SavedRun,
    WorkflowAccessLevel,
)
from daras_ai.image_input import truncate_text_words
from daras_ai_v2 import icons, settings

# Shared with v1 rather than copied. This module holds only what v2 changes or adds.
from daras_ai_v2.base import (
    MAX_SEED,
    SUBMIT_AFTER_LOGIN_Q,
    RecipeRunState,
    StateKeys,
    gooey_rng,
)
from daras_ai_v2.base import (
    BasePage as BasePageV1,
)
from daras_ai_v2.breadcrumbs import get_title_breadcrumbs
from daras_ai_v2.copy_to_clipboard_button_widget import copy_to_clipboard_button
from daras_ai_v2.crypto import get_random_doc_id
from daras_ai_v2.gooey_builder import (
    GOOEY_BUILDER_EVENT_KEY,
    GOOEY_BUILDER_TITLE,
    builder_thread_is_empty,
    can_launch_gooey_builder,
    get_gooey_builder_photo_url,
    render_gooey_builder,
)
from daras_ai_v2.grid_layout_widget import grid_layout
from daras_ai_v2.tab_spec import PaneSpec, RecipeView, TabSpec
from daras_ai_v2.variables_widget import variables_input
from functions.base_llm_tool import (
    BaseLLMTool,
    functions_input,
)
from functions.composio_tools import ComposioLLMTool
from functions.memory_tools import GooeyMemoryLLMTool
from functions.models import (
    FunctionScopes,
    FunctionTrigger,
)
from functions.workflow_tools import WorkflowLLMTool

# leaf modules - pydantic models only - so there is no cycle to dodge with a lazy import
from gooey_gui.types.recipe_top_bar_props import (
    RecipeTopBarProps,
    TopBarAuthor,
    TopBarIntegration,
    TopBarMenuItem,
    TopBarView,
)
from gooey_gui.types.recipe_workspace_props import (
    RecipeWorkspaceProps,
    WorkPane,
    WorkspacePaneControlProps,
)
from routers.root import RecipeTabs
from widgets.publish_form import clear_publish_form
from widgets.sidebar import sidebar_layout
from widgets.workflow_share import render_share_modal
from workspaces.models import Workspace


def format_credits_as_dollars(credits: int) -> str:
    """A credit count as the price a user pays, via the one conversion rate billing uses."""
    return f"${credits / settings.ADDON_CREDITS_PER_DOLLAR:.2f}"


class WorkflowIdentity(typing.NamedTuple):
    """How a run names and pictures itself: the pair the top bar leads with."""

    # With the tab's prefix: "Run: Farmer.AI".
    title: str
    # Without it, for tabs that put their own name in the crumb.
    name: str
    photo_url: str | None
    circle_photo: bool


class BasePage(BasePageV1):
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

        # App shell: a fixed-height bar over a body that scrolls inside itself. The bar's
        # node is reserved here so it comes first in the DOM, but filled at the end of this
        # method - the publish state is only settled once the inputs have rendered.
        top_bar_placeholder = gui.div(
            className=(
                # a CSS query container, so the bar's chips size against the bar's own
                # width rather than the viewport's
                "v2-topbar-container flex-shrink-0 w-100 px-2 px-lg-4 py-2"
            )
        )

        # The Builder sits beside the tab body rather than wrapping the page, so the bar
        # above can run the full width. Needs a definite height for the Sidebar's `h-100`
        # root to resolve against; `v2-app-shell` is what its CSS keys off.
        with gui.div(
            className="v2-app-shell d-flex flex-column flex-grow-1 w-100",
            style=dict(minHeight=0),
        ):
            builder_pane, body_pane = self._builder_layout()

        with (
            body_pane,
            gui.div(
                className=(
                    # h-100 not flex-grow-1: the Sidebar leaves no flex context to grow
                    # into. px-0 below lg so the panes run edge to edge, and no `pb-*` -
                    # clearing the run bar needs `env(safe-area-inset-bottom)`, which
                    # RecipeWorkspace.css owns.
                    "v2-workspace-body d-flex flex-column h-100 w-100 overflow-auto "
                    "px-0 pt-2 pt-lg-0 pb-lg-2"
                ),
                # or a flex child refuses to shrink below its content
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
        with gui.model_component(
            RecipeWorkspaceProps(
                storage_key=self._workspace_storage_key(),
                initial_view=self.entry_tab_slug(tabs),
                editor_full_width=self._editor_wants_full_width(),
                narrow_pane=self.narrow_pane(),
            )
        ):
            # framed surfaces need holding off the top bar's rule; the editor leads with
            # the pane strip, which brings its own spacing
            with gui.div(className="mt-1"):
                with gui.styled(ABOUT_CSS), gui.div(className="v2-about"):
                    self._render_about_content()

            with gui.div():
                if self._render_deleted_output_if_needed():
                    submitted = False
                else:
                    submitted = self._render_solo_input_col()

            # mt-lg-1 only: below lg the preview meets the header's rule directly
            with gui.div(className="mt-lg-1"):
                if self.current_sr.retention_policy == RetentionPolicy.delete:
                    self.render_deleted_output()
                else:
                    self._render_output_col(submitted=submitted)

    def _workflow_identity(self) -> WorkflowIdentity:
        """Derived once, so every part of the bar's heading agrees on the same run."""
        from widgets.workflow_image import CIRCLE_IMAGE_WORKFLOWS

        sr, pr = self.current_sr_pr
        tbreadcrumbs = get_title_breadcrumbs(self, sr, pr, tab=self.tab)
        fallback = self.get_run_title(sr, pr)
        return WorkflowIdentity(
            title=tbreadcrumbs.title_with_prefix() or fallback,
            name=(tbreadcrumbs.h1_title and tbreadcrumbs.h1_title.title) or fallback,
            photo_url=pr.photo_url or None,
            circle_photo=self.workflow in CIRCLE_IMAGE_WORKFLOWS,
        )

    def _editor_wants_full_width(self) -> bool:
        """Whether the open config pane needs the whole row.

        Server-side, because it depends on session state and both the workspace and the top
        bar have to agree on it.
        """
        return False

    def narrow_pane(self) -> WorkPane:
        """Which half of a two-pane view a phone shows.

        Per-recipe rather than a layout rule: a chat keeps the bot, a media recipe would keep
        the form. Both the workspace and the top bar fold on this, so it lives server-side.
        """
        if self.is_unowned_example():
            # A visitor's one work tab is "How it works", which exists to show config.
            return WorkPane.editor
        return WorkPane.preview

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
        """(builder pane, body pane), or `(None, dummy)` when the Builder is unavailable."""
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
        # The panel's collapse control, positioned against `.gooey-sidebar` at every
        # breakpoint so there is no app-header offset to hardcode.
        gui.model_component(
            WorkspacePaneControlProps(
                label="Close Ask gooey",
                icon=icons.cls.cancel,
                event_name=f"{GOOEY_BUILDER_EVENT_KEY}:close",
                className="v2-builder-close",
            )
        )
        # The panel's title, and its "new conversation" control - v2 hides the widget's own
        # header. Skipped on an empty thread, where the widget draws its own splash.
        if not builder_thread_is_empty(self):
            gui.model_component(
                WorkspacePaneControlProps(
                    label=GOOEY_BUILDER_TITLE,
                    # the label names the panel; the tooltip says what clicking it does
                    tooltip="New Chat",
                    photo_url=get_gooey_builder_photo_url(),
                    show_label=True,
                    event_name=f"{GOOEY_BUILDER_EVENT_KEY}:new",
                    # padding is owned by `.v2-pane-control-labelled`, not a utility class
                    className="v2-builder-new",
                )
            )
        render_gooey_builder(
            event_key=GOOEY_BUILDER_EVENT_KEY, request=self.request, page=self
        )

    def _handle_top_bar_actions(self):
        """Pop the keys RecipeTopBar wrote and act on them.

        The bar mutates session state and calls onChange(); the server sees the key on the
        next render.
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

        # Popped in the base, which is what ships `menu_key` and `title_menu_items`.
        self._handle_menu_pick(gui.session_state.pop(self.TOP_BAR_MENU_KEY, None))

    def _handle_menu_pick(self, picked: str | None):
        """Act on a title-menu pick, and keep whatever dialog it opened on screen.

        `picked` is only the render where the click arrives, so each dialog's `is_open` check
        sits outside its `picked ==` check. Recipes extend this and call `super()`.
        """
        history_ref = gui.use_alert_dialog(key="version-history-modal")
        if picked == self.MENU_VERSION_HISTORY:
            history_ref.set_open(True)
        if history_ref.is_open:
            with gui.alert_dialog(
                ref=history_ref,
                modal_title=f"#### {icons.time} Version History",
                large=True,
                unsafe_allow_html=True,
            ):
                self._render_version_history()

        delete_ref = gui.use_confirm_dialog(key="--delete-run-modal")
        if picked == self.MENU_DELETE:
            delete_ref.set_open(True)
        if delete_ref.is_open:
            with gui.confirm_dialog(
                ref=delete_ref,
                modal_title="#### Are you sure?",
                confirm_label="Delete",
                confirm_className="border-danger bg-danger text-white",
            ):
                gui.write(
                    f"Are you sure you want to delete **{self.current_pr.title}**?\n\n"
                    "This will also delete all the associated versions."
                )
        if delete_ref.pressed_confirm:
            self.current_pr.delete()
            raise gui.RedirectException(self.app_url())

        if picked == self.MENU_DUPLICATE:
            self._duplicate_and_redirect()

    def _duplicate_and_redirect(self) -> typing.NoReturn:
        """Copy this workflow into the current workspace and open the copy.

        Someone who can edit gets a straight copy; someone who cannot is forking a workflow
        that is not theirs, so the copy is named after them.
        """
        pr = self.current_pr
        if WorkflowAccessLevel.can_user_edit_published_run(
            workspace=self.current_workspace, user=self.request.user, pr=pr
        ):
            new_pr = self.create_published_run(
                published_run_id=get_random_doc_id(),
                saved_run=self.current_sr,
                user=self.request.user,
                workspace=self.current_workspace,
                tags=list(pr.tags.all()),
                title=f"{pr.title} (Copy)",
                notes="" if pr.is_root() else pr.notes,
            )
        else:
            new_pr = pr.duplicate(
                user=self.request.user,
                workspace=self.current_workspace,
                title=f"{self.request.user.first_name_possesive()} {pr.title}",
                notes=pr.notes,
            )
        raise gui.RedirectException(self.app_url(example_id=new_pr.published_run_id))

    def _handle_top_bar_run(self):
        """Run (or Stop) pressed in the top bar. Validates first and starts nothing if that
        fails; anonymous users go through `submit_and_redirect`'s login redirect."""
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

    # Picks from the title chevron, echoed back through `menu_key`. Namespaced so a recipe's
    # own menu keys cannot collide with the base's.
    MENU_VERSION_HISTORY = "--menu-version-history"
    MENU_DUPLICATE = "--menu-duplicate"
    MENU_DELETE = "--menu-delete"

    def _title_menu_items(self) -> list[TopBarMenuItem]:
        """The chevron menu beside the workflow name.

        Gated the same way v1 gates its Options dialog, so the menu never offers something
        the server would refuse.
        """
        if not self.is_logged_in():
            return []

        pr = self.current_pr
        items = []

        # A root recipe is the template every run forks from; it has no versions.
        if not pr.is_root():
            items.append(
                TopBarMenuItem(
                    key=self.MENU_VERSION_HISTORY,
                    label="Version history",
                    icon=icons.history,
                )
            )

        # "Duplicate" off the latest version, "Save as New" off an older one.
        items.append(
            TopBarMenuItem(
                key=self.MENU_DUPLICATE,
                label=(
                    "Duplicate" if pr.saved_run == self.current_sr else "Save as New"
                ),
                icon=icons.fork,
            )
        )

        if (
            self.request.user
            and WorkflowAccessLevel.can_user_delete_published_run(
                workspace=self.current_workspace,
                user=self.request.user,
                pr=pr,
            )
            and not pr.is_root()
        ):
            items.append(
                TopBarMenuItem(
                    key=self.MENU_DELETE,
                    label="Delete",
                    icon=icons.trash,
                )
            )

        return items

    def can_manage_sharing(self) -> bool:
        """Whether this user may change who can see the workflow, rather than only copy its
        url. Unlike v1 this does not require the url to point at the published run - the
        dialog edits `pr` either way and gates its own options by role."""
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
        """Share, outside the top bar. Sets the same key the bar's menu item sets, so
        `_handle_top_bar_actions` still owns the one dialog."""
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

    def _top_bar_cost(self) -> tuple[str, str]:
        """(label, hover note) for the bar's cost readout, in dollars."""
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
        sr, pr = self.current_sr_pr
        identity = self._workflow_identity()
        cost_label, cost_title = self._top_bar_cost()
        can_manage_sharing = self.can_manage_sharing()
        workspace_active = self.tab in {RecipeTabs.run, RecipeTabs.preview}
        # a root recipe has no published run behind it, so there is no published url to share
        can_share = not pr.is_root()

        gui.model_component(
            RecipeTopBarProps(
                # Prefixed on the workspace; elsewhere the tab's label is the crumb.
                title=identity.title if workspace_active else identity.name,
                crumb_label="" if workspace_active else (self.tab.label or ""),
                view_only=self.is_unowned_example(),
                photo_url=identity.photo_url,
                circle_photo=identity.circle_photo,
                author=self._top_bar_author(),
                storage_key=self._workspace_storage_key(),
                initial_view=self.entry_tab_slug(tabs),
                editor_full_width=self._editor_wants_full_width(),
                narrow_pane=self.narrow_pane(),
                workspace_href=self.current_app_url(RecipeTabs.run),
                workspace_active=workspace_active,
                views=[
                    TopBarView(
                        slug=tab.slug,
                        label=tab.label,
                        icon=tab.icon,
                        desktop_only=tab.desktop_only,
                    )
                    for tab in tabs
                ],
                publish_label=self._top_bar_publish_label(),
                publish_key=self.TOP_BAR_PUBLISH_KEY,
                api_href=self.current_app_url(RecipeTabs.run_as_api),
                deploy_href=self.current_app_url(RecipeTabs.integrations),
                # Exactly one of these is set, and neither on a root recipe.
                share_key=(
                    self.TOP_BAR_SHARE_KEY if can_share and can_manage_sharing else ""
                ),
                share_copy_url=(
                    self.current_app_url(self.tab)
                    if can_share and not can_manage_sharing
                    else ""
                ),
                share_icon=icons.share,
                has_unpublished_changes=self._has_request_changed()
                or (self.can_user_save_run(sr, pr) and pr.saved_run != sr),
                menu_key=self.TOP_BAR_MENU_KEY,
                title_menu_items=self._title_menu_items(),
                integrations=self._top_bar_integrations(),
                run_key=self.TOP_BAR_RUN_KEY,
                is_running=self._is_run_in_progress(),
                cost_label=cost_label,
                cost_href=self.get_credits_click_url(),
                cost_title=cost_title,
                builder_event_key=(
                    GOOEY_BUILDER_EVENT_KEY if self._can_show_builder() else ""
                ),
                # Below lg the bar is the app's only header and carries these; inert above.
                # Empty on a thread that has not started - the same gate the panel uses.
                builder_new_event=(
                    f"{GOOEY_BUILDER_EVENT_KEY}:new"
                    if self._can_show_builder() and not builder_thread_is_empty(self)
                    else ""
                ),
                history_href=self.current_app_url(RecipeTabs.history),
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

    def _render_pane_strip(
        self, panes: list[PaneSpec], *, key: str
    ) -> typing.Callable[[], None]:
        """Render an in-page strip of panes and return the one to draw.

        Panes are panels within one view, so they have no url - an ordered list of specs and
        a session-state key, which carries `PaneSpec.id` rather than the label.

        Only the active pane renders. Widgets on the others keep their values because the
        whole `session_state` round-trips regardless of what was drawn, so a pane must read
        `gui.session_state` rather than another pane's return value.
        """
        by_id = {pane.id: pane for pane in panes}

        # Deep links write this key directly (see `RecipeWorkspaceTrigger.state_key`), so
        # only an absent or stale value needs settling.
        if gui.session_state.get(key) not in by_id:
            gui.session_state[key] = panes[0].id

        with gui.styled(PANE_STRIP_CSS), gui.div(className="mb-1"):
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

    def get_tab_spec(self) -> list[TabSpec]:
        """The client views for this request, in selector order."""
        if self.is_unowned_example():
            return self.get_viewer_tab_spec()
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

    def get_viewer_tab_spec(self) -> list[TabSpec]:
        """What a first-time visitor sees. Two entries, since they own nothing here to edit;
        "How it works" is backed by `split` so the configuration shows beside a live
        preview."""
        return [
            TabSpec(
                slug=RecipeView.about,
                label="About",
                icon=icons.info,
            ),
            TabSpec(
                slug=RecipeView.split,
                label="How it works",
                icon=icons.edit,
            ),
        ]

    def _render_about_content(self):
        """What this workflow is. Version history lives in the title menu and Related
        Workflows on /explore/, so neither appears here."""
        pr = self.current_pr
        # The portrait leads; the top bar carries the title and author line.
        self._render_about_photo(pr)
        # description and the cards share one panel - two levels of the same answer
        with gui.div(className="v2-about-panel"):
            # full text: this tab is made to be read
            if pr.notes:
                with gui.div(className="container-margin-reset v2-about-notes"):
                    gui.write(pr.notes)
            self._render_about_meta()
            self._render_about_deployments()

    def _render_about_photo(self, pr: PublishedRun):
        """The workflow's portrait. `CIRCLE_IMAGE_WORKFLOWS` get a round crop, matching the
        top bar and the rail."""
        from widgets.workflow_image import CIRCLE_IMAGE_WORKFLOWS

        if not pr.photo_url:
            return
        circle = self.workflow in CIRCLE_IMAGE_WORKFLOWS
        gui.html(
            f'<img class="v2-about-photo{" v2-about-photo-circle" if circle else ""}"'
            f' src="{html.escape(pr.photo_url)}" alt="">'
        )

    def _render_about_meta(self):
        """Hook: cards summarising how this workflow is put together. Per-recipe, so the
        base renders nothing."""

    def _render_about_deployments(self):
        """The channels this workflow is live on, as cards beside Model and Tools.

        Its own `.v2-about-groups` row, since `_render_about_meta` is a per-recipe override a
        base surface cannot reach into.
        """
        integrations = self._top_bar_integrations()
        if not integrations:
            return
        with (
            gui.div(className="v2-about-groups"),
            gui.div(className="v2-about-group"),
        ):
            gui.html('<div class="v2-about-section-title">Deployments</div>')
            with gui.div(className="v2-about-meta"):
                for it in integrations:
                    body = (
                        f'<span class="v2-about-meta-icon">{it.icon}</span>'
                        f'<span class="v2-about-meta-label">{html.escape(it.label)}</span>'
                    )
                    # A channel with no url opens a dialog from the bar, not from here.
                    if it.href:
                        gui.html(
                            f'<a class="v2-about-meta-card"'
                            f' href="{html.escape(it.href)}">{body}</a>'
                        )
                    else:
                        gui.html(f'<div class="v2-about-meta-card">{body}</div>')

    def _render_solo_input_col(self) -> bool:
        """The working column alone, through the same `gui.columns` wrapper Split uses so
        gutters, background and pane height match without being kept in sync by hand."""
        with gui.styled(INPUT_OUTPUT_COLS_CSS + SPLIT_PANES_CSS):
            (input_col,) = gui.columns([1])
            with (
                input_col,
                # Centred and capped for reading width; Split needs none, the preview caps
                # it there. Flex + `minHeight: 0` keeps the definite-height chain intact.
                gui.div(
                    className="v2-reading-col h-100 d-flex flex-column px-2 px-lg-0",
                    style=dict(minHeight=0),
                ),
            ):
                return self._render_input_col()

    def _preview_frame(self):
        """Frames the preview when it shares the view. Alone it needs none - a border there
        would just outline the viewport."""
        # By class, not inline, so the frame can be dropped below lg where the preview runs
        # edge to edge.
        return gui.div(className="h-100 v2-preview-frame")

    def _render_split_tab(self):
        """Both columns side by side. Only the columns: an app shell has no page scroll to
        put anything below them, so the guide lives on About and Debug on a config pane."""
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
                with gui.div(className="v2-reading-col"):
                    self.run_as_api_tab()

            case RecipeTabs.saved:
                self._saved_tab()

    def render_related_workflows(self):
        page_clses = self.related_workflows()
        if not page_clses:
            return

        with gui.link(to="/explore/"):
            gui.html("<h2>Related Workflows</h2>")

        def _render(page_cls: type[BasePage]):
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

    def get_run_cost_display(self) -> str:
        url = self.get_credits_click_url()
        run_cost = self.get_run_cost_credits()
        if run_cost is not None:
            # dollars, matching the top bar's readout
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
        """Names the variables editor must not offer: request/response fields and function
        slugs, which have inputs of their own. Shared with `variable_names()`."""
        function_slugs = [
            slug
            for fn in gui.session_state.get("functions", [])
            if (slug := fn.get("slug"))
        ]
        return self.fields_to_save() + function_slugs

    def _render_variables_editor(self, *, heading: bool = True):
        """`heading=False` where the surface already names itself. An empty label also drops
        the help tooltip, which the dialog's own intro replaces."""
        variables_input(
            template_keys=self.template_keys,
            # Ungated: a variable needs no function, and the functions switch is on
            # another pane here, so gating on it would read as a missing button.
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

    def _render_output_col(self, *, submitted: bool = False, is_deleted: bool = False):
        assert inspect.isgeneratorfunction(self.run)

        if gui.session_state.get(StateKeys.pressed_randomize):
            gui.session_state["seed"] = int(gooey_rng.randrange(MAX_SEED))
            gui.session_state.pop(StateKeys.pressed_randomize, None)
            submitted = True

        if submitted:
            self.submit_and_redirect()

        # A flex column: the notices around the output - failure box, cancelled warning,
        # run spinner - size to themselves, and the output takes what is left. The pane
        # clips rather than scrolls, so a child claiming the full height would push the
        # bottom of the output out of reach. `minHeight: 0` at every level, or a flex child
        # refuses to shrink below its content.
        with gui.div(
            className="d-flex flex-column " + self._output_col_class_name(),
            style=dict(height="100%", minHeight=0),
        ):
            run_state = self.get_run_state(gui.session_state)
            if run_state == RecipeRunState.failed:
                self._render_failed_output()

            # render outputs
            if not is_deleted:
                self.render_is_cancelled()
                with gui.div(
                    className="flex-grow-1 d-flex flex-column",
                    style=dict(minHeight=0),
                ):
                    self.render_output()

            if run_state in (RecipeRunState.running, RecipeRunState.starting):
                self._render_running_output()
            elif not is_deleted:
                self._render_after_output()

    def _output_col_class_name(self) -> str:
        """The client-side Preview view controls visibility at every breakpoint."""
        return ""

    def submit_and_redirect(
        self,
        unsaved_state: dict[str, typing.Any] | None = None,
        **defaults,
    ):
        sr = self.on_submit(unsaved_state=unsaved_state, **defaults)
        if not sr:
            return

        raise gui.RedirectException(self.app_url(run_id=sr.run_id, uid=sr.uid))

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

    def _render_regenerate_button(self):
        if "seed" in self.RequestModel.schema_json():
            randomize = gui.button(f"{icons.regenerate} Regenerate", type="tertiary")
            if randomize:
                gui.session_state[StateKeys.pressed_randomize] = True
                gui.rerun()


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
    border-bottom: 1px solid var(--gooey-line-soft);
}

& button {
    flex: 0 0 auto;
    /* inline-flex keeps the active dot on the same line as the label; with inline-block it
       becomes a block-level box and the label drops to a second line */
    display: inline-flex !important;
    align-items: center;
    white-space: nowrap !important;
    margin: 0 !important;
    padding: 8px 12px !important;
    border: 1px solid var(--gooey-line-soft) !important;
    border-radius: 10px !important;
    background: var(--gooey-bg-page) !important;
    color: var(--gooey-ink-muted) !important;
    font-weight: 500 !important;
    line-height: 120% !important;
    font-size: 14px !important;
}

& button:hover {
    background: var(--gooey-bg-page) !important;
    border-color: var(--gooey-line-strong) !important;
    color: var(--gooey-ink) !important;
}

& button.pane-active {
    border-color: var(--gooey-line-strong) !important;
    color: var(--gooey-ink) !important;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
    background: var(--gooey-surface-100) !important;
}

& button.pane-active::before {
    content: "";
    flex: 0 0 auto;
    width: 6px;
    height: 6px;
    margin-right: 8px;
    border-radius: 50%;
    background: var(--gooey-ink);
}

/* Below lg the strip is the first thing under the app header, and the editor's surface starts
   at the header's rule - so `my-1`'s top margin was the last 4px of page background showing
   through between the two. The bottom half stays: that is what holds the strip's own rule off
   the pills, and leaves room for the active pill's shadow. `!important` to beat the utility. */
@media (max-width: 991.98px) {
    & {
        margin-top: 0 !important;
    }
}
"""

SPLIT_PANES_CSS = """
/* App-shell panes. The row fills the body exactly, so the body never overflows and therefore
   never scrolls; the left pane scrolls inside itself and the right pane (the preview) stays
   put.

   This used to stop at lg, on the reasoning that a stacked phone layout may as well scroll
   the page. But the shell is the frame at every width, and cutting the height chain here cut
   it for everything below: with no definite height on the column, the `h-100` inside it
   resolves to `auto`, the working column's `flex-grow-1 overflow-auto` pane never gets a
   bound to scroll against, and it grows to fit its content instead - so a short pane like
   Knowledge or Tools still scrolled the whole section, and the strip and submit row went with
   it. Bounded at every width, `overflow: auto` does what it says: nothing scrolls until the
   content is actually taller than the pane. */
& {
    margin: 0;
    padding-top: 0;
    height: 100%;
    min-height: 0;
}

/* Neither column scrolls as a whole. The left column is a flex stack whose *pane* scrolls,
   so its strip and submit row stay put; the right column is the preview, which manages its
   own scrolling. */
& > div {
    height: 100%;
    min-height: 0;
    overflow: hidden;
}

@media (min-width: 992px) {
    & > div {
        /* the working column starts at the page's own padding, with no gutter on top of it -
           on the row's children, because a wrapper div around `with input_col:` would mount
           beside the row, not around the columns */
        padding-left: 0px;
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
    /* set col padding in mobile */
    & > div {
        padding-left: calc(var(--bs-gutter-x) * .5);
        padding-right: calc(var(--bs-gutter-x) * .5);
    }
}
"""

# The About tab. `!important` on the buttons because the app's own button styling is more
# specific than a scoped `& button` rule.
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

/* No card around this content. The pane it sits in is already a surface, so a white box
   inside it was a second frame around the same thing - only the description panel and the
   meta chips carry their own background now. */

/* The portrait leads, centred and large: the top bar names the workflow, so this is what
   identifies it here. `CIRCLE_IMAGE_WORKFLOWS` (agents) get a round crop. */
& .v2-about-photo {
    display: block;
    width: 15rem;
    height: 15rem;
    max-width: 100%;
    object-fit: cover;
    border-radius: 16px;
    margin: 0.5rem auto 1.5rem;
}

& .v2-about-photo-circle {
    border-radius: 50%;
}

/* Description and the meta groups share one tinted panel - they answer "what is this" at two
   levels of detail. Only the cards inside carry their own surface. */
& .v2-about-panel {
    background: var(--gooey-surface-100);
    border-radius: 16px;
    padding: 1.5rem;
}

& .v2-about-notes {
    color: var(--gooey-ink);
    margin-bottom: 1.5rem;
}

/* Model and Tools & Integrations, side by side while there is room. Model holds one card, so
   it takes only what it needs and the integrations group gets the rest. */
& .v2-about-groups {
    display: flex;
    flex-wrap: wrap;
    gap: 1.5rem;
}

/* Sizes to its own cards. With `min-width: 0` the group could be squeezed narrower than one
   card, which made the cards inside wrap into a column while the row still looked half empty.
   Whole groups wrap instead. */
& .v2-about-group {
    flex: 0 1 auto;
    min-width: min-content;
}

& .v2-about-section-title {
    /* names the group - plain and dark, since it labels content rather than decorating it */
    font-size: 0.9375rem;
    font-weight: 500;
    color: var(--gooey-ink);
    margin: 0 0 0.5rem 0;
}

/* `nowrap`: a group's cards belong on one line, and the group is what gives way when the row
   runs out of width. Below lg they stack - see the media query at the end. */
& .v2-about-meta {
    display: flex;
    flex-wrap: nowrap;
    gap: 0.75rem;
}

/* Icon above label, not beside it: the label is the longer of the two and wraps, so a row
   layout made every card as tall as its text anyway. Fixed width so a set of one lines up
   with a set of three. */
& .v2-about-meta-card {
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    gap: 1.25rem;
    /* One fixed width for every card, so a one-card group lines up with a three-card one.
       `min-width: 0` is what makes that stick: a flex item defaults to `min-width: auto`,
       which resolves to the label's min-content width, and a min-width beats a max-width -
       so without it each card grew to fit its own text and no two matched. */
    flex: 0 0 11rem;
    min-width: 0;
    padding: 0.875rem;
    border: 1px solid var(--gooey-line-default);
    border-radius: 12px;
    background: var(--gooey-surface-50);
    color: var(--gooey-ink);
    text-decoration: none;
    transition: border-color 0.12s ease, box-shadow 0.12s ease;
}

& .v2-about-meta-card:hover {
    border-color: var(--gooey-line-strong);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
    color: var(--gooey-ink);
}

/* No chip behind it: at this size the glyph and a model creator's colour logo both read
   fine on the card itself, and the extra surface only muddied a card that is already a
   surface. */
& .v2-about-meta-icon {
    display: inline-flex;
    align-items: center;
    font-size: 1.5rem;
    line-height: 1;
    color: var(--gooey-ink);
}

& .v2-about-meta-icon img {
    height: 1.5rem;
    width: 1.5rem;
    object-fit: contain;
}

& .v2-about-meta-label {
    min-width: 0;
    font-size: 0.9375rem;
    line-height: 1.3;
    /* a long name ellipsises rather than wrapping, so every card in a row is the same height */
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

@media (max-width: 991.98px) {
    /* One column: side by side there is not room for two groups plus their cards, and the
       cards were being squeezed to the point the labels all ellipsised. */
    & .v2-about-groups {
        flex-direction: column;
        gap: 1.25rem;
    }

    /* the group is full width now, so its cards may wrap within it */
    & .v2-about-meta {
        flex-wrap: wrap;
    }

    /* `1 1 0` rather than a basis: the cards share the row evenly instead of each taking its
       own content width, so they stay equal here too */
    & .v2-about-meta-card {
        flex: 1 1 0;
    }

    /* clears the tab pills, which below lg float over the bottom of the viewport rather than
       sitting in the top bar */
    & .v2-about-panel {
        margin-bottom: 4.5rem;
    }
}
"""
