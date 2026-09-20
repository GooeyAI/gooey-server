from __future__ import annotations

from typing import Annotated, ClassVar, Literal

import pydantic

from gooey_gui.types import StrictComponentModel
from gooey_gui.types.recipe_workspace_props import WorkspaceLayout


class AboutAuthor(StrictComponentModel):
    """Who published the workflow, above the panel."""

    name: str
    photo_url: str
    # empty when the workspace has published nothing else worth counting
    subtitle: str | None = None
    # a workspace without a handle is named but not linked
    href: str | None = None


class AboutTag(StrictComponentModel):
    """One filing pill. The tag renders its own label - it carries an emoji or a flag - so
    that arrives as markup rather than text."""

    label_html: str
    href: str


class AboutVideoMedia(StrictComponentModel):
    kind: Literal["video"] = "video"
    url: str


class AboutBannerMedia(StrictComponentModel):
    kind: Literal["banner"] = "banner"
    url: str


class AboutPhotoMedia(StrictComponentModel):
    """The square portrait About has always drawn. Now the last of three media states
    rather than a field of its own, so the surface has one slot."""

    kind: Literal["photo"] = "photo"
    url: str
    circle: bool = False


AboutMedia = Annotated[
    AboutVideoMedia | AboutBannerMedia | AboutPhotoMedia,
    pydantic.Field(discriminator="kind"),
]


class AboutMoreInfo(StrictComponentModel):
    """The outbound link beside Share, e.g. "View case study"."""

    text: str
    href: str


class AboutSDG(StrictComponentModel):
    """One UN goal tile. The icon carries the goal's number, title and colour, so the tile
    draws the image alone."""

    number: int
    title: str
    icon_url: str
    href: str


class AboutStat(StrictComponentModel):
    value: str
    label: str


class AboutStats(StrictComponentModel):
    title: str
    cards: list[AboutStat] = []


class AboutPaneTarget(StrictComponentModel):
    """Opens a config pane in the workspace beside About."""

    kind: Literal["pane"] = "pane"
    layout: WorkspaceLayout
    editor_pane: str | None = None


class AboutLinkTarget(StrictComponentModel):
    kind: Literal["link"] = "link"
    href: str


class AboutSubmitTarget(StrictComponentModel):
    """Posts an intent through the page's form, which is how the top bar's chips open their
    dialogs - `value` is the already-encoded intent."""

    kind: Literal["submit"] = "submit"
    value: str


AboutCardTarget = Annotated[
    AboutPaneTarget | AboutLinkTarget | AboutSubmitTarget,
    pydantic.Field(discriminator="kind"),
]


class AboutCard(StrictComponentModel):
    """One tile: a mark, a chevron, and a label under them."""

    icon_html: str
    label: str
    target: AboutCardTarget


class AboutGroup(StrictComponentModel):
    """A heading and the grid of cards under it."""

    title: str
    cards: list[AboutCard] = []


class RecipeAboutProps(StrictComponentModel):
    """Everything the About surface draws. Structured rather than pre-rendered html, so the
    component owns the markup and the payload carries only what varies."""

    _component: ClassVar[Literal["RecipeAbout"]] = "RecipeAbout"

    media: AboutMedia | None = None
    headline: str | None = None

    author: AboutAuthor | None = None
    # the encoded pick that opens the report dialog, or None with nobody to attribute it to
    report_value: str | None = None
    # the encoded ShareIntent, or None with no share dialog to open
    share_value: str | None = None
    # the url for the browser's own share sheet, set instead of `share_value` for a visitor
    # who has no dialog - the two are never both present
    share_url: str | None = None
    submit_intent_key: str

    tags: list[AboutTag] = []
    # markdown, clamped to `notes_line_clamp` lines with an expander
    notes: str | None = None
    notes_line_clamp: int = 6

    groups: list[AboutGroup] = []
    more_info: AboutMoreInfo | None = None
    sdgs: list[AboutSDG] = []
    stats: AboutStats | None = None
