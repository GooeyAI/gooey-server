import typing

from gooey_gui.types.recipe_workspace_props import (
    SingleLayout,
    SplitLayout,
    SurfaceId,
    WorkspaceLayout,
    WorkspaceView,
)

__all__ = [
    "PaneSpec",
    "SingleLayout",
    "SplitLayout",
    "SurfaceId",
    "TabSpec",
    "WorkspaceLayout",
]


class PaneSpec(typing.NamedTuple):
    """One panel of the working column.

    `id` is the pane's identity - it goes into session state and into
    `RecipeWorkspaceTrigger` deep links, so it must stay stable. `label` is display-only.
    """

    id: str
    label: str
    render: typing.Callable[[], None]


class TabSpec(WorkspaceView):
    pass
