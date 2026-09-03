from __future__ import annotations

from typing import Annotated, ClassVar, Literal

import pydantic

from gooey_gui.types import StrictComponentModel
from gooey_gui.types.recipe_workspace_props import PageShellConfig


class RunIntent(StrictComponentModel):
    kind: Literal["run"] = "run"


class StopIntent(StrictComponentModel):
    kind: Literal["stop"] = "stop"


class PublishIntent(StrictComponentModel):
    kind: Literal["publish"] = "publish"


class ShareIntent(StrictComponentModel):
    kind: Literal["share"] = "share"


class MenuIntent(StrictComponentModel):
    kind: Literal["menu"] = "menu"
    item_key: str


RecipeSubmitIntent = Annotated[
    RunIntent | StopIntent | PublishIntent | ShareIntent | MenuIntent,
    pydantic.Field(discriminator="kind"),
]

RunControlIntent = Annotated[
    RunIntent | StopIntent,
    pydantic.Field(discriminator="kind"),
]


class LinkTarget(StrictComponentModel):
    kind: Literal["link"] = "link"
    href: str


class SubmitTarget(StrictComponentModel):
    kind: Literal["submit"] = "submit"
    intent: RecipeSubmitIntent


TopBarTarget = Annotated[
    LinkTarget | SubmitTarget,
    pydantic.Field(discriminator="kind"),
]


class TopBarAuthor(StrictComponentModel):
    label: str


class TopBarIntegration(StrictComponentModel):
    key: str
    label: str
    icon_html: str
    target: TopBarTarget
    color: str | None = None


class TopBarMenuItem(StrictComponentModel):
    key: str
    label: str
    target: TopBarTarget
    icon_html: str | None = None
    is_danger: bool = False


class NoShare(StrictComponentModel):
    kind: Literal["none"] = "none"


class CopyShare(StrictComponentModel):
    kind: Literal["copy"] = "copy"
    url: str
    icon_html: str


class ManageShare(StrictComponentModel):
    kind: Literal["manage"] = "manage"
    intent: ShareIntent = pydantic.Field(default_factory=ShareIntent)
    icon_html: str


ShareControl = Annotated[
    NoShare | CopyShare | ManageShare,
    pydantic.Field(discriminator="kind"),
]


class RecipeTopBarProps(StrictComponentModel):
    _component: ClassVar[Literal["RecipeTopBar"]] = "RecipeTopBar"

    config: PageShellConfig
    title: str
    # Where the heading points, from `get_title_breadcrumbs` - the workflow this run belongs
    # to. None when the title already names the page you are on.
    title_href: str | None = None
    photo_url: str | None = None
    circle_photo: bool = False
    author: TopBarAuthor | None = None

    title_menu_items: list[TopBarMenuItem] = pydantic.Field(default_factory=list)
    integrations: list[TopBarIntegration] = pydantic.Field(default_factory=list)

    submit_intent_key: str
    publish_label: str | None = None
    publish_intent: PublishIntent | None = None
    has_unpublished_changes: bool = False
    api_href: str | None = None
    deploy_href: str | None = None
    share: ShareControl = pydantic.Field(default_factory=NoShare)

    view_only: bool = False
    crumb_label: str | None = None
    builder_panel_key: str | None = None
    builder_new_event: str | None = None
    # Usage is a route rather than a client-side pane, but it shares the bar's view
    # selector. None hides it for viewers who cannot inspect the workflow's run data.
    usage_href: str | None = None
    usage_active: bool = False

    # None where the bar carries no run control at all: Usage reports on runs already made,
    # so it offers neither Run nor the cost of one.
    run_intent: RunControlIntent | None = None
    cost_label: str | None = None
    cost_href: str | None = None
    cost_title: str | None = None


class EditorRunBarProps(StrictComponentModel):
    """The same Run control, at the foot of the editor pane rather than in the bar.

    Here rather than beside the workspace's own props for `RunControlIntent`: that module is
    imported by this one, so reaching back for the intents would close a cycle.
    """

    _component: ClassVar[Literal["EditorRunBar"]] = "EditorRunBar"

    submit_intent_key: str
    run_intent: RunControlIntent
    cost_label: str | None = None
    cost_href: str | None = None
    cost_title: str | None = None
