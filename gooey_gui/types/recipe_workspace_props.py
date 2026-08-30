from __future__ import annotations

from enum import Enum
from typing import Annotated, ClassVar, Literal

import pydantic

from gooey_gui.types import StrictComponentModel


class SurfaceId(str, Enum):
    about = "about"
    editor = "editor"
    preview = "preview"


class SingleLayout(StrictComponentModel):
    kind: Literal["single"] = "single"
    surface: SurfaceId


class SplitLayout(StrictComponentModel):
    kind: Literal["split"] = "split"
    primary: SurfaceId
    secondary: SurfaceId

    @pydantic.model_validator(mode="after")
    def validate_distinct_surfaces(self) -> SplitLayout:
        if self.primary == self.secondary:
            raise ValueError("A split layout requires two different surfaces")
        return self


WorkspaceLayout = Annotated[
    SingleLayout | SplitLayout,
    pydantic.Field(discriminator="kind"),
]


class WorkspaceView(StrictComponentModel):
    key: str
    label: str
    icon_html: str | None = None
    layout: WorkspaceLayout
    desktop_only: bool = False


class PageShellConfig(StrictComponentModel):
    storage_key: str
    initial_layout: WorkspaceLayout
    run_layout: WorkspaceLayout
    route_layout: WorkspaceLayout | None = None
    views: list[WorkspaceView] = pydantic.Field(default_factory=list)
    narrow_surface: SurfaceId = SurfaceId.preview
    workspace_href: str
    workspace_active: bool
    active_run_id: str | None = None

    @pydantic.model_validator(mode="after")
    def validate_views(self) -> PageShellConfig:
        if not self.views:
            raise ValueError("Page shell requires at least one view")
        keys = [view.key for view in self.views]
        if len(keys) != len(set(keys)):
            raise ValueError("Page shell view keys must be unique")
        if self.initial_layout not in [view.layout for view in self.views]:
            raise ValueError("Initial layout must match a declared view")
        if self.run_layout not in [view.layout for view in self.views]:
            raise ValueError("Run layout must match a declared view")
        if not layout_contains(self.run_layout, self.narrow_surface):
            raise ValueError("Narrow surface must be present in the run layout")
        return self


class RecipeWorkspaceProps(StrictComponentModel):
    _component: ClassVar[Literal["RecipeWorkspace"]] = "RecipeWorkspace"

    config: PageShellConfig


class RecipeSurfaceProps(StrictComponentModel):
    _component: ClassVar[Literal["RecipeSurface"]] = "RecipeSurface"

    surface: SurfaceId


class SessionStateUpdate(StrictComponentModel):
    key: str
    value: str


class RecipeWorkspaceTriggerProps(StrictComponentModel):
    _component: ClassVar[Literal["RecipeWorkspaceTrigger"]] = "RecipeWorkspaceTrigger"

    layout: WorkspaceLayout
    state_update: SessionStateUpdate | None = None
    className: str | None = None


class FontAwesomeIcon(StrictComponentModel):
    kind: Literal["font_awesome"] = "font_awesome"
    class_name: str


class PhotoIcon(StrictComponentModel):
    kind: Literal["photo"] = "photo"
    url: str


ControlIcon = Annotated[
    FontAwesomeIcon | PhotoIcon,
    pydantic.Field(discriminator="kind"),
]


class PanelControlTarget(StrictComponentModel):
    kind: Literal["panel"] = "panel"
    panel_key: str
    open: bool


class EventControlTarget(StrictComponentModel):
    kind: Literal["event"] = "event"
    event_name: str


ControlTarget = Annotated[
    PanelControlTarget | EventControlTarget,
    pydantic.Field(discriminator="kind"),
]


class WorkspacePaneControlProps(StrictComponentModel):
    _component: ClassVar[Literal["WorkspacePaneControl"]] = "WorkspacePaneControl"

    label: str
    icon: ControlIcon
    target: ControlTarget
    tooltip: str | None = None
    show_label: bool = False
    className: str | None = None


def layout_contains(layout: WorkspaceLayout, surface: SurfaceId) -> bool:
    if isinstance(layout, SingleLayout):
        return layout.surface == surface
    return surface in {layout.primary, layout.secondary}
