from __future__ import annotations

import pydantic


class TopBarTab(pydantic.BaseModel):
    """One tab in the bar's pill group. Mirrors the display half of `TabSpec` - the
    `render` callable never leaves the server.
    """

    slug: str
    label: str
    icon: str = ""  # raw FontAwesome html, like NavItemData.icon
    href: str
    is_active: bool = False
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
    """An entry in the title chevron menu or the tab overflow."""

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
    builder_close_event: str = ""
    builder_open: bool = False

    tabs: list[TopBarTab] = []
    # the active tab owns the screen below lg, so the strip and the run cluster
    # step out of the way and the tab supplies its own way back
    immersive_on_mobile: bool = False
    overflow_items: list[TopBarMenuItem] = []  # the "..." beside the pill group
    title_menu_items: list[TopBarMenuItem] = []  # the chevron beside the title

    integrations: list[TopBarIntegration] = []

    publish_label: str = ""  # permission-derived: Update / Save and Run / Save as New
    publish_key: str = ""  # set by the client to open the publish dialog
    has_unpublished_changes: bool = False

    # Only set when the user may actually change who can see the workflow - everyone else
    # gets a copy-link button elsewhere rather than a visibility dialog they cannot use.
    share_key: str = ""
    share_icon: str = ""  # reflects current visibility: a globe, a lock, ...

    # Written by the client and popped by the server on the next render, the same
    # mutate-then-notify contract NavigationSidebar uses for workspace switching.
    menu_key: str = ""
    run_key: str = ""

    # Written by the client whenever the viewport crosses lg, and never popped: the server
    # cannot see the viewport, but it has to know whether the desktop-only tabs are on
    # screen before it redirects anyone to one. See `BasePage.TOP_BAR_WIDE_KEY`.
    viewport_wide_key: str = ""

    run_label: str = "Run"
    run_disabled: bool = False
    is_running: bool = False  # swaps Run for Stop
    cost_label: str = ""  # e.g. "$0.10"
    cost_href: str = ""
    # per-recipe cost notes (e.g. "+1 (lipsync)"), shown on hover rather than inline so a
    # long note cannot push the Run button around
    cost_title: str = ""
