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


class TopBarAuthor(pydantic.BaseModel):
    """The "by <someone>" line under the title."""

    label: str  # e.g. "by Opportunity International" or "Remix by James"
    href: str | None = None
    photo_url: str | None = None


class TopBarIntegration(pydantic.BaseModel):
    """A connected channel, surfaced as a shortcut pill next to Publish."""

    label: str
    icon: str  # raw FontAwesome html, e.g. icons.whatsapp
    href: str
    color: str | None = None  # brand colour for the pill, e.g. WhatsApp green


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

    tabs: list[TopBarTab] = []
    overflow_items: list[TopBarMenuItem] = []  # the "..." beside the pill group
    title_menu_items: list[TopBarMenuItem] = []  # the chevron beside the title

    integrations: list[TopBarIntegration] = []

    publish_label: str = ""  # permission-derived: Update / Save and Run / Save as New
    publish_key: str = ""  # set by the client to open the publish dialog
    has_unpublished_changes: bool = False

    # Written by the client and popped by the server on the next render, the same
    # mutate-then-notify contract NavigationSidebar uses for workspace switching.
    menu_key: str = ""
    run_key: str = ""

    run_label: str = "Run"
    run_disabled: bool = False
    is_running: bool = False  # swaps Run for Stop
    cost_label: str = ""  # e.g. "$0.10"
    cost_href: str = ""
    # per-recipe cost notes (e.g. "+1 (lipsync)"), shown on hover rather than inline so a
    # long note cannot push the Run button around
    cost_title: str = ""

    # toggles the Gooey Builder panel; reuses the builder's own event key
    builder_toggle_key: str = ""
