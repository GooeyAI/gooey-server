import typing

import pydantic

from gooey_gui.types.recipe_workspace_props import RecipeView

# Re-exported: `RecipeView` is defined next to the props that carry it into TypeScript, so
# the generator can emit it as a named union. Recipes still import it from here, where the
# rest of the tab vocabulary lives.
__all__ = ["PaneSpec", "RecipeView", "TabSpec"]


class PaneSpec(typing.NamedTuple):
    """One panel of the working column.

    `id` and `label` are deliberately separate. The id is the pane's identity - it is what
    goes into session state and into the `RecipeWorkspaceTrigger` deep links the About cards
    build - so it has to stay stable. The label is display-only and free to change. Keying a
    pane by its label instead meant renaming the label silently broke every deep link
    pointing at it, with no error: the strip just fell back to the first pane.
    """

    id: str
    label: str
    render: typing.Callable[[], None]


class TabSpec(pydantic.BaseModel):
    """One client-side view in the layout-v2 workspace selector."""

    slug: RecipeView
    """View identity; it is deliberately not a URL segment."""

    label: str
    icon: str = ""
    """Raw FontAwesome html, like `NavItemData.icon`."""

    desktop_only: bool = False
    """Hidden from the strip below `lg`. For tabs whose layout needs the width - Split is
    two columns side by side, which a phone cannot show."""
