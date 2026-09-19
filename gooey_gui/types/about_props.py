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
    # A platform's own colour, for the deployment buttons below lg. None keeps it neutral.
    accent: str | None = None


class AboutGroup(StrictComponentModel):
    """A heading and the grid of cards under it.

    `variant` is what lets the deployments read as full-width buttons below lg, where the
    design puts them under the description rather than in the card grid.
    """

    title: str
    cards: list[AboutCard] = []
    variant: Literal["cards", "deployments"] = "cards"


class RecipeAboutProps(StrictComponentModel):
    """Everything the About surface draws. Structured rather than pre-rendered html, so the
    component owns the markup and the payload carries only what varies."""

    _component: ClassVar[Literal["RecipeAbout"]] = "RecipeAbout"

    # The workflow's name and run count, shown below lg where the bar leads with the logo
    # instead. Not the page's h1 - that is the top bar's, and there is only one.
    heading: str
    heading_meta: str | None = None

    photo_url: str | None = None
    circle_photo: bool = False

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
