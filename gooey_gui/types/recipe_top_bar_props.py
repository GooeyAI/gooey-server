from __future__ import annotations

import pydantic

from gooey_gui.types.recipe_workspace_props import RecipeView, WorkPane


class TopBarView(pydantic.BaseModel):
    """One client-side workspace arrangement in the bar's view selector."""

    slug: RecipeView
    label: str
    icon: str = ""  # raw FontAwesome html, like NavItemData.icon
    desktop_only: bool = False  # hidden below lg; see TabSpec.desktop_only


class TopBarAuthor(pydantic.BaseModel):
    """The "by <someone>" line under the title."""

    label: str  # e.g. "by Opportunity International" or "Remix by James"
    href: str | None = None
    photo_url: str | None = None


class TopBarIntegration(pydantic.BaseModel):
    """A connected channel, surfaced as a shortcut chip next to Publish.

    Either a link (`href`) or a server action (`key`, echoed back through `menu_key`) -
    VideoBots' demo buttons open a dialog rather than navigating.
    """

    label: str
    icon: str  # raw FontAwesome html, e.g. icons.whatsapp
    href: str | None = None
    key: str = ""
    color: str | None = None  # brand colour for the chip, e.g. WhatsApp green


class TopBarMenuItem(pydantic.BaseModel):
    """An entry in the title chevron menu or the view overflow."""

    key: str  # echoed back through `menu_key` so the server knows what was picked
    label: str
    icon: str = ""
    href: str | None = None  # a link when set, otherwise a server action via `menu_key`
    is_danger: bool = False


class RecipeTopBarProps(pydantic.BaseModel):
    _component: str = "RecipeTopBar"

    title: str
    photo_url: str | None = None
    circle_photo: bool = False  # some workflows render the avatar as a circle
    author: TopBarAuthor | None = None

    views: list[TopBarView] = []
    storage_key: str
    initial_view: RecipeView
    # The open config pane has taken the whole row, so the bar names the arrangement on
    # screen rather than the split still saved behind it.
    editor_full_width: bool = False
    # Must match RecipeWorkspaceProps.narrow_pane: the bar names the arrangement that is on
    # screen, so it has to fold a two-pane view the same way the workspace does.
    narrow_pane: WorkPane = WorkPane.preview
    workspace_href: str
    workspace_active: bool
    overflow_items: list[TopBarMenuItem] = []  # the "..." beside the pill group
    title_menu_items: list[TopBarMenuItem] = []  # the chevron beside the title

    integrations: list[TopBarIntegration] = []

    publish_label: str = ""  # permission-derived: Update / Save and Run / Save as New
    publish_key: str = ""  # set by the client to open the publish dialog
    has_unpublished_changes: bool = False
    # The recipe's API tab, offered from the Publish menu: calling the workflow over HTTP is
    # another way to ship it, alongside saving and sharing. A link, not an action.
    api_href: str = ""

    # Only set when the user may actually change who can see the workflow; everyone else gets
    # `share_copy_url` instead of a visibility dialog they cannot use.
    share_key: str = ""
    share_icon: str = ""  # reflects current visibility: a globe, a lock, ...
    # The counterpart for a viewer: the url to copy. Set only when `share_key` is not, so the
    # bar always offers Share one way or the other.
    share_copy_url: str = ""

    # Written by the client and popped by the server on the next render, the same
    # mutate-then-notify contract NavigationSidebar uses for workspace switching.
    menu_key: str = ""
    run_key: str = ""

    # ---------------------------------------------------------------- mobile only
    # Below lg this bar is the app's ONLY header: the sidebar's own mobile bar is hidden and
    # the floating pill strip is gone, so the bar inherits the controls both used to carry.
    # Both are inert above lg. The nav drawer's own open command is not here - it is a
    # constant in navDrawer.ts, shared by the two client components that use it, because
    # nothing server-side changes when the drawer opens.

    # A visitor looking at somebody else's run: nothing here is theirs to edit, publish or
    # deploy. The bar drops all of it and offers the three things that do apply - read it, see
    # how it works, make one of your own.
    view_only: bool = False
    # What the header's crumb reads on a tab that is not the workspace - API, Deploy. Those
    # are levels above the editor rather than arrangements of it, so the client cannot name them
    # from `views`; and their name already exists as the tab's own label. Empty on the
    # workspace, where the active view is the crumb.
    crumb_label: str = ""
    # Deploy, which is a route rather than a pane: `/integrations/` renders the same surface,
    # and a config pane that needed the whole row was competing with the preview for it.
    deploy_href: str = ""

    # The Builder panel's event key, so the bar can tell whether Ask Gooey is on screen and
    # put it back. Below lg the panel is the root of a navigation stack, which makes its open
    # state the difference between the header showing a menu button and showing a back arrow -
    # the bar cannot infer that from the pane layout, because the panel is not a pane.
    # Empty when this page has no Builder, in which case the entry view is the root instead.
    builder_event_key: str = ""
    # Starts a fresh Ask Gooey thread. Empty when there is no Builder on this page, or when
    # its thread has not started yet - "New Chat" is a no-op on an empty chat, the same
    # condition the panel's own control uses.
    builder_new_event: str = ""
    # Version History, offered in the mobile action sheet. A plain url, so it needs no key
    # round-trip. Empty hides the entry.
    history_href: str = ""

    run_label: str = "Run"
    run_disabled: bool = False
    is_running: bool = False  # swaps Run for Stop
    cost_label: str = ""  # e.g. "$0.10"
    cost_href: str = ""
    # per-recipe cost notes (e.g. "+1 (lipsync)"), shown on hover rather than inline so a
    # long note cannot push the Run button around
    cost_title: str = ""
