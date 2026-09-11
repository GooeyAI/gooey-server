from __future__ import annotations

from typing import Annotated, Literal

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


class AboutGroup(StrictComponentModel):
    """A heading and the grid of cards under it."""

    title: str
    cards: list[AboutCard] = []


class RecipeAboutProps(pydantic.BaseModel):
    """Everything the About surface draws. Structured rather than pre-rendered html, so the
    component owns the markup and the payload carries only what varies."""

    _component: str = "RecipeAbout"

    # The page's one h1, visually hidden: the top bar already shows the name, but that bar
    # is chrome on every tab, so it cannot be the heading.
    heading: str

    photo_url: str | None = None
    circle_photo: bool = False

    author: AboutAuthor | None = None
    # the encoded ShareIntent, or None when there is nothing shareable
    share_value: str | None = None
    submit_intent_key: str

    tags: list[AboutTag] = []
    # markdown, clamped to `notes_line_clamp` lines with an expander
    notes: str | None = None
    notes_line_clamp: int = 6

    groups: list[AboutGroup] = []
