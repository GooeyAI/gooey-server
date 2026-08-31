import html
import inspect
import typing
from functools import cached_property

import pydantic

import gooey_gui as gui
from bots.models import (
    PublishedRun,
    RetentionPolicy,
    SavedRun,
    WorkflowAccessLevel,
)
from daras_ai_v2 import icons, settings
from daras_ai_v2.base import (
    BasePage as BasePageV1,
)
from daras_ai_v2.base import (
    RecipeRunState,
    StateKeys,
)
from daras_ai_v2.breadcrumbs import get_title_breadcrumbs
from daras_ai_v2.crypto import get_random_doc_id
from daras_ai_v2.gooey_builder import (
    GOOEY_BUILDER_EVENT_KEY,
    GOOEY_BUILDER_TITLE,
    builder_thread_is_empty,
    can_launch_gooey_builder,
    get_gooey_builder_photo_url,
    render_gooey_builder,
)
from daras_ai_v2.tab_spec import (
    PaneSpec,
    SingleLayout,
    SplitLayout,
    SurfaceId,
    TabSpec,
    WorkspaceLayout,
)
from daras_ai_v2.urls import paginate_queryset
from daras_ai_v2.variables_widget import variables_input
from functions.base_llm_tool import functions_input
from gooey_gui.types.recipe_top_bar_props import (
    CopyShare,
    EditorRunBarProps,
    LinkTarget,
    ManageShare,
    MenuIntent,
    NoShare,
    PublishIntent,
    RecipeSubmitIntent,
    RecipeTopBarProps,
    RunIntent,
    ShareIntent,
    StopIntent,
    SubmitTarget,
    TopBarAuthor,
    TopBarIntegration,
    TopBarMenuItem,
)
from gooey_gui.types.recipe_workspace_props import (
    EventControlTarget,
    FontAwesomeIcon,
    PageShellConfig,
    PanelControlTarget,
    PhotoIcon,
    RecipeSurfaceProps,
    RecipeWorkspaceProps,
    WorkspacePaneControlProps,
)
from gooey_gui.types.run_grid_props import RunGridProps
from routers.root import RecipeTabs
from widgets.history import load_more_href
from widgets.publish_form import clear_publish_form
from widgets.sidebar import sidebar_layout
from widgets.workflow_cards import author_from_user, history_card
from widgets.workflow_share import render_share_modal
from workspaces.models import Workspace

RUN_GRID_PAGE_SIZE = 24

# About's description, before it gives way to a "more" link. Enough to say what a workflow is
# without pushing the cards below it off the screen unread.
ABOUT_NOTES_LINE_CLAMP = 6


def format_credits_as_dollars(credits: int) -> str:
    """A credit count as the price a user pays, via the one conversion rate billing uses."""
    return f"${credits / settings.ADDON_CREDITS_PER_DOLLAR:.2f}"


class WorkflowIdentity(typing.NamedTuple):
    """How a run names and pictures itself: the pair the top bar leads with."""

    # With the tab's prefix: "Run: Farmer.AI".
    title: str
    # Without it, for tabs that put their own name in the crumb.
    name: str
    # The workflow this run belongs to, or None when the heading already names this page.
    href: str | None
    photo_url: str | None
    circle_photo: bool


class BasePage(BasePageV1):
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

        tabs = self.get_tab_spec()
        assert tabs, f"{type(self).__name__}.get_tab_spec() returned no tabs"
        shell_config = self._page_shell_config(tabs)

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
                className=self._workspace_body_class(shell_config),
                # or a flex child refuses to shrink below its content
                style=dict(minHeight=0),
            ),
        ):
            if shell_config.workspace_active:
                self._render_workspace(shell_config)
            else:
                self.render_selected_tab()

        if builder_pane is not None:
            with builder_pane:
                self._render_gooey_builder()

        with top_bar_placeholder:
            self._render_top_bar(config=shell_config)

        self._handle_top_bar_actions()

    def _page_shell_config(self, tabs: list[TabSpec]) -> PageShellConfig:
        workspace_active = self.tab in {RecipeTabs.run, RecipeTabs.preview}
        route_layout = None
        if self.tab == RecipeTabs.preview:
            route_layout = SingleLayout(surface=SurfaceId.preview)

        active_run_id = None
        if workspace_active:
            active_run_id = self.request.query_params.get("run_id") or None

        return PageShellConfig(
            storage_key=self._workspace_storage_key(),
            initial_layout=self.entry_layout(tabs),
            run_layout=self.work_layout(),
            route_layout=route_layout,
            views=tabs,
            narrow_surface=self.narrow_surface(),
            workspace_href=self.current_app_url(RecipeTabs.run),
            workspace_active=workspace_active,
            active_run_id=active_run_id,
        )

    def _workspace_body_class(self, config: PageShellConfig) -> str:
        body = "v2-workspace-body d-flex flex-column h-100 w-100 pt-2 pt-lg-0 pb-lg-2"
        if config.workspace_active:
            return f"{body} overflow-auto px-0"
        return body

    def _render_workspace(self, config: PageShellConfig):
        """Render each reusable work surface once; React controls their arrangement."""
        with gui.model_component(RecipeWorkspaceProps(config=config)):
            # framed surfaces need holding off the top bar's rule; the editor leads with
            # the pane strip, which brings its own spacing
            with (
                gui.model_component(RecipeSurfaceProps(surface=SurfaceId.about)),
                gui.div(className="mt-1"),
            ):
                with gui.styled(ABOUT_CSS), gui.div(className="v2-about"):
                    self._render_about_content()

            with (
                gui.model_component(RecipeSurfaceProps(surface=SurfaceId.editor)),
                gui.div(),
            ):
                if self._render_deleted_output_if_needed():
                    submitted = False
                else:
                    submitted = self._render_solo_input_col()

            # mt-lg-1 only: below lg the preview meets the header's rule directly
            with (
                gui.model_component(RecipeSurfaceProps(surface=SurfaceId.preview)),
                gui.div(className="mt-lg-1"),
            ):
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
            # v1 draws this as the linked half of its breadcrumb, and leaves it empty on the
            # page the heading names - so a run points at its workflow, and the workflow's
            # own page points nowhere.
            href=(tbreadcrumbs.h1_title and tbreadcrumbs.h1_title.url) or None,
            photo_url=pr.photo_url or None,
            circle_photo=self.workflow in CIRCLE_IMAGE_WORKFLOWS,
        )

    def narrow_surface(self) -> SurfaceId:
        """Which half of a two-pane view a phone shows.

        Per-recipe rather than a layout rule: a chat keeps the bot, a media recipe would keep
        the form. Both the workspace and the top bar fold on this, so it lives server-side.
        """
        if self.is_view_only():
            # Their one work tab is "How it works", which exists to show config.
            return SurfaceId.editor
        return SurfaceId.preview

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
                icon=FontAwesomeIcon(class_name=icons.cls.cancel),
                target=PanelControlTarget(
                    panel_key=GOOEY_BUILDER_EVENT_KEY,
                    open=False,
                ),
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
                    icon=PhotoIcon(url=get_gooey_builder_photo_url()),
                    target=EventControlTarget(
                        event_name=f"{GOOEY_BUILDER_EVENT_KEY}:new"
                    ),
                    show_label=True,
                    # padding is owned by `.v2-pane-control-labelled`, not a utility class
                    className="v2-builder-new",
                )
            )
        render_gooey_builder(
            event_key=GOOEY_BUILDER_EVENT_KEY, request=self.request, page=self
        )

    def _handle_top_bar_actions(self):
        if self.tab == RecipeTabs.usage:
            # nothing on this tab submits, and a stale key from the workspace would fire
            # against a run the reader is not looking at
            gui.session_state.pop(self.SUBMIT_INTENT_KEY, None)
            return

        intent = self._pop_submit_intent()
        publish_ref = gui.use_alert_dialog(key="publish-modal")

        if isinstance(intent, PublishIntent):
            if self.is_logged_in():
                clear_publish_form()
                publish_ref.set_open(True)
            else:
                self._publish_for_anonymous_user()

        if publish_ref.is_open:
            self._render_publish_dialog(ref=publish_ref)

        # the one Share dialog on the page: the bar's button and About's both set the key
        share_ref = gui.use_alert_dialog(key="share-modal")
        if isinstance(intent, ShareIntent):
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

        if isinstance(intent, (RunIntent, StopIntent)):
            self._handle_top_bar_run(intent)

        menu_key = intent.item_key if isinstance(intent, MenuIntent) else None
        self._handle_menu_pick(menu_key)

    def _pop_submit_intent(self) -> RecipeSubmitIntent | None:
        raw_intent = gui.session_state.pop(self.SUBMIT_INTENT_KEY, None)
        if not raw_intent:
            return None

        adapter = pydantic.TypeAdapter(RecipeSubmitIntent)
        try:
            if isinstance(raw_intent, str):
                return adapter.validate_json(raw_intent)
            return adapter.validate_python(raw_intent)
        except (pydantic.ValidationError, ValueError, TypeError):
            gui.error("Invalid workflow action. Please refresh and try again.")
            return None

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
                modal_title=f"#### {icons.time} Versions",
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

    def _handle_top_bar_run(self, intent: RunIntent | StopIntent):
        if isinstance(intent, StopIntent):
            if not self._is_run_in_progress():
                return
            self.current_sr.is_cancelled = True
            self.current_sr.save(update_fields=["is_cancelled", "updated_at"])
            raise gui.RerunException()

        if self._is_run_in_progress():
            return

        try:
            self.validate_form_v2()
        except AssertionError as e:
            gui.error(str(e))
            return

        self.submit_and_redirect()

    def entry_layout(self, tabs: list[TabSpec]) -> WorkspaceLayout:
        """The view the workspace opens on. About for a view-only viewer, the work split for
        anyone who can update the app.

        Read off the same answer `get_tab_spec` reads, so the landing view and the tabs
        offered cannot disagree: a view-only viewer is given About and How it works, and How
        it works is a config form they have no way to save. About is what their half of the
        tab set is for, so it is where they start - the root of a recipe and a published run
        they cannot update alike.
        """
        if self.is_view_only():
            return tabs[0].layout
        return self.work_layout()

    def work_layout(self) -> WorkspaceLayout:
        """The two-pane working view: the editor with its preview beside it."""
        return SplitLayout(primary=SurfaceId.editor, secondary=SurfaceId.preview)

    @cached_property
    def can_edit_current_pr(self) -> bool:
        """Whether this workflow is the viewer's to change: its creator, a member of its
        workspace holding EDIT access, a workspace admin, or a staff admin. A root recipe
        belongs to nobody, so it answers False for everyone but a staff admin.

        Cached because the answer costs a membership and a workspace-admin query, and the
        page asks it once per surface it decides.
        """
        if not self.request.user:
            return False
        try:
            workspace = self.current_workspace
        except Workspace.DoesNotExist:
            return False
        return WorkflowAccessLevel.can_user_edit_published_run(
            workspace=workspace, user=self.request.user, pr=self.current_pr
        )

    def is_view_only(self) -> bool:
        """The url points at a published workflow the viewer cannot update, rather than at a
        run of it. They get the tabs that present the workflow instead of the ones that
        change it.

        Permission, not authorship: a workspace holds its apps in common, so a member with
        EDIT access reads as an editor here even on an app somebody else published. A run of
        an app is always the viewer's to work on, which is why the url has to point at the
        published run itself for this to answer True.
        """
        sr, pr = self.current_sr_pr
        return pr.saved_run_id == sr.id and not self.can_edit_current_pr

    SUBMIT_INTENT_KEY = "--recipe-submit-intent"

    # Stable item keys carried by MenuIntent.
    MENU_VERSION_HISTORY = "--menu-version-history"
    MENU_DUPLICATE = "--menu-duplicate"
    MENU_DELETE = "--menu-delete"

    def _title_menu_items(self) -> list[TopBarMenuItem]:
        """Menu actions available to the current user."""
        if not self.is_logged_in():
            return []

        pr = self.current_pr
        items = []

        # A root recipe is the template every run forks from; it has no versions.
        if not pr.is_root():
            items.append(
                TopBarMenuItem(
                    key=self.MENU_VERSION_HISTORY,
                    label="Versions",
                    icon_html=icons.history,
                    target=SubmitTarget(
                        intent=MenuIntent(item_key=self.MENU_VERSION_HISTORY)
                    ),
                )
            )

        # "Duplicate" off the latest version, "Save as New" off an older one.
        items.append(
            TopBarMenuItem(
                key=self.MENU_DUPLICATE,
                label=(
                    "Duplicate" if pr.saved_run == self.current_sr else "Save as New"
                ),
                icon_html=icons.fork,
                target=SubmitTarget(intent=MenuIntent(item_key=self.MENU_DUPLICATE)),
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
                    icon_html=icons.trash,
                    target=SubmitTarget(intent=MenuIntent(item_key=self.MENU_DELETE)),
                    is_danger=True,
                )
            )

        return items

    def can_manage_sharing(self) -> bool:
        """Whether this user may edit workflow visibility."""
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

    def _render_top_bar(self, *, config: PageShellConfig):
        sr, pr = self.current_sr_pr
        identity = self._workflow_identity()
        cost_label, cost_title = self._top_bar_cost()
        can_manage_sharing = self.can_manage_sharing()
        # a root recipe has no published run behind it, so there is no published url to share
        can_share = not pr.is_root()
        share = NoShare()
        if can_share and can_manage_sharing:
            share = ManageShare(icon_html=icons.share)
        elif can_share:
            share = CopyShare(
                url=self.current_app_url(self.tab),
                icon_html=icons.share,
            )

        is_running = self._is_run_in_progress()

        usage_active = self.tab == RecipeTabs.usage

        gui.model_component(
            RecipeTopBarProps(
                config=config,
                # Prefixed on the workspace; elsewhere the tab's label is the crumb.
                title=identity.title if config.workspace_active else identity.name,
                title_href=identity.href,
                crumb_label=None if config.workspace_active else self.tab.label,
                view_only=self.is_view_only(),
                photo_url=identity.photo_url,
                circle_photo=identity.circle_photo,
                author=self._top_bar_author(),
                submit_intent_key=self.SUBMIT_INTENT_KEY,
                publish_label=self._top_bar_publish_label(),
                publish_intent=PublishIntent(),
                api_href=self.current_app_url(RecipeTabs.run_as_api),
                deploy_href=self.current_app_url(RecipeTabs.integrations),
                share=share,
                has_unpublished_changes=self._has_request_changed()
                or (self.can_user_save_run(sr, pr) and pr.saved_run != sr),
                title_menu_items=self._title_menu_items(),
                integrations=self._top_bar_integrations(),
                run_intent=StopIntent() if is_running else RunIntent(),
                cost_label=None if usage_active else (cost_label or None),
                cost_href=(
                    None if usage_active else (self.get_credits_click_url() or None)
                ),
                cost_title=None if usage_active else (cost_title or None),
                builder_panel_key=(
                    GOOEY_BUILDER_EVENT_KEY if self._can_show_builder() else None
                ),
                builder_new_event=(
                    f"{GOOEY_BUILDER_EVENT_KEY}:new"
                    if self._can_show_builder() and not builder_thread_is_empty(self)
                    else None
                ),
                # a route rather than a pane, and empty for anyone who cannot read the
                # workflow's run data
                usage_href=self._usage_href(),
                usage_active=usage_active,
            )
        )

    def _usage_href(self) -> str | None:
        """The Usage tab's url, or None to leave it out of the bar.

        Two rights, and both are needed: updating the app puts the editing tabs in the bar,
        and belonging to the workspace is what makes its run list readable. A view-only
        viewer gets About and How it works, which present the workflow; a list of its runs
        is an editor's tool and does not belong beside them. The route itself stays open, so
        a link to it still resolves.
        """
        if self.is_view_only() or not self.can_view_usage():
            return None
        return self.current_app_url(RecipeTabs.usage)

    def _top_bar_author(self):
        """The "by <someone>" line. Workspace when there is one, else the run's user."""

        pr = self.current_pr
        if pr.workspace_id and not pr.workspace.is_personal:
            return TopBarAuthor(
                label=f"by {pr.workspace.display_name(self.request.user)}",
            )
        user = self.current_sr_user
        if user:
            return TopBarAuthor(
                label=f"by {user.display_name or user.first_name(fallback='User')}",
            )
        return None

    def _top_bar_publish_label(self) -> str:
        """Permission-derived label for the publish action."""
        if not self.is_logged_in():
            return "Save"
        if self.can_edit_current_pr:
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

    def get_tab_spec(self) -> list[TabSpec]:
        if self.is_view_only():
            return self.get_viewer_tab_spec()
        return [
            TabSpec(
                key="about",
                label="About",
                icon_html=icons.info,
                layout=SplitLayout(
                    primary=SurfaceId.about,
                    secondary=SurfaceId.preview,
                ),
            ),
            TabSpec(
                key="edit",
                label="Edit",
                icon_html=icons.edit,
                layout=SingleLayout(surface=SurfaceId.editor),
            ),
            TabSpec(
                key="preview",
                label="Preview",
                icon_html=icons.preview,
                layout=SingleLayout(surface=SurfaceId.preview),
            ),
            TabSpec(
                key="split",
                label="Split",
                icon_html=icons.run,
                layout=SplitLayout(
                    primary=SurfaceId.editor,
                    secondary=SurfaceId.preview,
                ),
            ),
        ]

    def get_viewer_tab_spec(self) -> list[TabSpec]:
        return [
            TabSpec(
                key="about",
                label="About",
                icon_html=icons.info,
                layout=SplitLayout(
                    primary=SurfaceId.about,
                    secondary=SurfaceId.preview,
                ),
            ),
            TabSpec(
                key="how-it-works",
                label="How it works",
                icon_html=icons.edit,
                layout=SplitLayout(
                    primary=SurfaceId.editor,
                    secondary=SurfaceId.preview,
                ),
            ),
        ]

    def _render_about_content(self):
        """What this workflow is. Version history lives in the title menu and Related
        Workflows on /explore/, so neither appears here."""
        pr = self.current_pr
        # The portrait leads, with the owner under it; the top bar carries the title.
        self._render_about_photo(pr)
        self._render_about_author(pr)
        # A panel each, rather than one holding both: the description is prose to read and
        # the cards are a spec to scan, and sharing a box made the cards read as a footnote
        # to the text above them.
        if pr.notes:
            with gui.div(className="v2-about-panel"):
                # the same heading the meta groups carry, so the two panels read as a pair
                gui.html('<div class="v2-about-section-title">Description</div>')
                with gui.div(className="container-margin-reset v2-about-notes"):
                    gui.write(pr.notes, line_clamp=ABOUT_NOTES_LINE_CLAMP)
        # `.v2-about-panel:empty` hides this for a recipe with neither cards nor
        # deployments, which is what the base `_render_about_meta` renders.
        with gui.div(className="v2-about-panel"):
            self._render_about_meta()
            self._render_about_deployments()

    def _render_about_author(self, pr: PublishedRun):
        """Who published this, under the portrait and below lg only.

        Above lg the top bar's author line already says it. Below lg that line is dropped for
        width, which left the workflow unattributed on a phone - the one place About is the
        whole page rather than half of it. Read off `pr.workspace` like the bar's line is, so
        the two cannot name different owners.
        """
        from widgets.author import render_author_from_workspace

        if not pr.workspace_id:
            return
        try:
            current_workspace = self.current_workspace
        except Workspace.DoesNotExist:
            current_workspace = None
        with gui.div(className="v2-about-author d-lg-none"):
            render_author_from_workspace(
                pr.workspace,
                image_size="32px",
                # the block never renders above lg, so there is no second size to scale to
                responsive=False,
                current_workspace=current_workspace,
            )

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
                    gui.html(self._about_deployment_card(it))

    def _about_deployment_card(self, it: TopBarIntegration) -> str:
        """One channel, carrying the same target as its chip in the bar."""
        body = (
            f'<span class="v2-about-meta-icon">{it.icon_html}</span>'
            f'<span class="v2-about-meta-label">{html.escape(it.label)}</span>'
        )
        if isinstance(it.target, LinkTarget):
            return (
                f'<a class="v2-about-meta-card"'
                f' href="{html.escape(it.target.href)}">{body}</a>'
            )
        # The page's form copies its submitter's name and value into the state it posts, so
        # a plain submit button reaches `_pop_submit_intent` by the same route the chip does
        # and `_handle_menu_pick` opens the same dialog.
        return (
            f'<button type="submit" class="v2-about-meta-card"'
            f' name="{html.escape(self.SUBMIT_INTENT_KEY)}"'
            f' value="{html.escape(it.target.intent.model_dump_json())}">{body}</button>'
        )

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
                submitted = self._render_input_col()
                self._render_editor_run_bar()
                return submitted

    def _render_editor_run_bar(self):
        """Run, and what it will cost, at the foot of the form that submits.

        In the editor's own column rather than pinned to the viewport, so it is bounded by
        the pane and needs no height reserved behind it. Drawn below lg only, which is where
        the bar above hides its own Run and cost; the component decides that.
        """
        cost_label, cost_title = self._top_bar_cost()
        # after `_render_input_col`, so a run this very request started already reads as
        # running and the button offers Stop - the point in the cycle the bar reads it at too
        is_running = self._is_run_in_progress()
        gui.model_component(
            EditorRunBarProps(
                submit_intent_key=self.SUBMIT_INTENT_KEY,
                run_intent=StopIntent() if is_running else RunIntent(),
                cost_label=cost_label or None,
                cost_href=self.get_credits_click_url() or None,
                cost_title=cost_title or None,
            )
        )

    def _render_deleted_output_if_needed(self) -> bool:
        """True if this run's data is gone, in which case that is all there is to render."""
        if self.current_sr.retention_policy != RetentionPolicy.delete:
            return False
        self.render_deleted_output()
        return True

    def render_selected_tab(self):
        """Render document-style tabs reached by URL."""
        match self.tab:
            case RecipeTabs.examples:
                self._examples_tab()

            case RecipeTabs.history:
                self._history_tab()

            case RecipeTabs.usage:
                self._usage_tab()

            case RecipeTabs.run_as_api:
                with gui.div(className="v2-reading-col"):
                    self.run_as_api_tab()

            case RecipeTabs.saved:
                self._saved_tab()

    def _usage_tab(self):
        # the bar only offers this tab to those who can read it, so anyone arriving without
        # the right is doing it by URL - `is_user_authorized` cannot answer for them, since a
        # public app is viewable by anyone while its run list is not
        if not self.can_view_usage():
            self.render_unauthorized(owner_workspace=self._usage_workspace())
            return

        qs = SavedRun.objects.filter(
            workflow=self.workflow,
            workspace=self._usage_workspace(),
            parent_version__published_run=self.current_pr,
        ).select_related(
            "parent_version__published_run",
            "workflow_metadata",
            "created_by",
            "message_thread__bot_conversation",
        )
        runs, next_cursor = paginate_queryset(
            qs=qs,
            ordering=["-updated_at"],
            cursor=self.request.query_params,
            page_size=RUN_GRID_PAGE_SIZE,
        )
        gui.model_component(
            RunGridProps(
                cards=[
                    history_card(
                        sr, author=author_from_user(sr.created_by, self.request.user)
                    )
                    for sr in runs
                ],
                load_more_href=load_more_href(self.request, next_cursor),
                empty_message="No usage yet.",
            )
        )

    def can_view_usage(self) -> bool:
        """The tab lists one workspace's runs, so seeing it means belonging to that workspace.

        Deliberately not "owns the current run": a run of somebody else's app belongs to the
        viewer, but the list it unlocks is scoped to the app's workspace, not theirs. The
        publisher and the workspace members are the same people as `cached_workspaces`, so
        there is nothing left for a `created_by` clause to admit.
        """
        user = self.request.user
        if self.is_user_admin(user):
            return True
        if not user or user.is_anonymous:
            return False
        return self._usage_workspace() in user.cached_workspaces

    def _usage_workspace(self) -> Workspace:
        """Whose runs the tab lists: the app's workspace, or the viewer's on a root recipe."""
        published_run = self.current_pr
        if not published_run.is_root() and published_run.workspace_id:
            return published_run.workspace
        return self.current_workspace

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

        if submitted:
            self.submit_and_redirect()

        # A flex column: the notices around the output - failure box, cancelled warning,
        # run spinner - size to themselves, and the output takes what is left. The pane
        # clips rather than scrolls, so a child claiming the full height would push the
        # bottom of the output out of reach. `minHeight: 0` at every level, or a flex child
        # refuses to shrink below its content.
        with gui.div(
            className="d-flex flex-column",
            style=dict(height="100%", minHeight=0),
        ):
            run_state = self.get_run_state(gui.session_state)
            if run_state == RecipeRunState.failed:
                # Its own scroller: the pane clips rather than scrolls, so a long message -
                # a traceback, a provider's error body - ran off the bottom with no way to
                # reach the rest of it. Capped so it cannot crowd out the output either.
                with gui.div(className="v2-run-error"):
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

    def submit_and_redirect(
        self,
        unsaved_state: dict[str, typing.Any] | None = None,
        **defaults,
    ):
        sr = self.on_submit(unsaved_state=unsaved_state, **defaults)
        if not sr:
            return

        raise gui.RedirectException(self.app_url(run_id=sr.run_id, uid=sr.uid))


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

/* `.gui-input` spaces one field from the next, which an editor told to fill its parent has
   no use for - there is nothing after it inside the pane. It showed as a strip of white
   between the editor and the run bar below it, the bar having moved into the flow. */
& .code-editor-wrapper {
    margin-bottom: 0;
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
/* Keep the height chain definite at every breakpoint so inner panes own scrolling. */
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

# Matches `.v2-about-meta-icon` below. Icon html that carries its own inline size - a model
# creator's logo, say - has to be asked for this one, since inline beats the stylesheet.
ABOUT_META_ICON_SIZE = "1.5rem"

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

/* Who published this, pulled up into the portrait's bottom margin so the two read as one
   heading block. Below lg only - `d-lg-none` on the element, since above lg the top bar's
   author line says the same thing and this would repeat it. */
& .v2-about-author {
    display: flex;
    justify-content: center;
    margin: -0.75rem 0 1.5rem;
}

/* One panel per kind of answer: the description is prose to read, the meta groups are a spec
   to scan. Only the cards inside carry their own surface. */
& .v2-about-panel {
    background: var(--gooey-surface-100);
    border-radius: 16px;
    padding: 1.5rem;
}

& .v2-about-panel + .v2-about-panel {
    margin-top: 1rem;
}

/* The meta panel is opened before its contents are known - `_render_about_meta` is a
   per-recipe hook and the base renders nothing - so a recipe with no cards and no
   deployments would leave an empty tinted box under the description. */
& .v2-about-panel:empty {
    display: none;
}

& .v2-about-notes {
    color: var(--gooey-ink);
    /* The clamp's "…more" is drawn over the tail of the last line, so it carries an opaque
       background to cover it - white by default, which read as a chip against this panel. */
    --line-clamp-bg: var(--gooey-surface-100);
}

/* Model and Tools & Integrations, side by side while there is room. Model holds one card, so
   it takes only what it needs and the integrations group gets the rest. */
& .v2-about-groups {
    display: flex;
    flex-wrap: wrap;
    gap: 1.5rem;
}

/* `_render_about_meta` and `_render_about_deployments` each emit a row of their own, and a
   flex `gap` only spaces a container's own children - so without this Deployments sat flush
   against the cards above it while the groups inside one row were properly spaced. */
& .v2-about-groups + .v2-about-groups {
    margin-top: 1.5rem;
}

/* Sizes to its own cards. With `min-width: 0` the group could be squeezed narrower than one
   card, which made the cards inside wrap into a column while the row still looked half empty.
   Whole groups wrap instead. */
& .v2-about-group {
    flex: 0 1 auto;
    min-width: min-content;
}

& .v2-about-section-title {
    /* Names the section rather than saying anything itself, so it is set back from what it
       labels - the cards and the description are what should be read first. */
    font-size: 0.9375rem;
    font-weight: 500;
    color: var(--gooey-ink-muted);
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
    --v2-about-card-width: 11rem;
    flex: 0 0 var(--v2-about-card-width);
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

/* For icon html that arrives without a size of its own; anything carrying an inline one
   wins here and has to be asked for ABOUT_META_ICON_SIZE instead. */
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

    /* matches the gap the groups inside a row use here */
    & .v2-about-groups + .v2-about-groups {
        margin-top: 1.25rem;
    }

    /* the group is full width now, so its cards may wrap within it */
    & .v2-about-meta {
        flex-wrap: wrap;
    }

    /* `1 1 0` rather than a basis: the cards share the row evenly instead of each taking its
       own content width, so they stay equal here too. Capped at the width they have above
       lg, or a group holding one card stretched it the whole width of the panel. */
    & .v2-about-meta-card {
        flex: 1 1 0;
        max-width: var(--v2-about-card-width);
    }

    & {
        /* Clears the tab pills, which below lg float over the bottom of the viewport rather
           than sitting in the top bar. On the container rather than the last panel: whether
           the meta panel is the last *rendered* box depends on whether it was hidden as
           empty, and a `:last-child` rule reads the DOM, not what is displayed. */
        padding-bottom: 4.5rem;
        /* The panels are the full width of the pane, which put their edges hard against the
           viewport's. Matches the `px-2` the editor column carries at this width, so the
           content edge holds still when the two tabs are switched between. */
        padding-left: 0.5rem;
        padding-right: 0.5rem;
    }
}
"""
