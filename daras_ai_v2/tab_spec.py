import typing
from enum import Enum

import pydantic


# `(str, Enum)` rather than `enum.StrEnum`: this runs on 3.10, where StrEnum does not exist.
class RecipeView(str, Enum):
    """The client-side views of the layout-v2 workspace.

    These ids cross into TypeScript: they must stay in step with the `RecipeView` union in
    `gooey-gui/app/components/RecipeWorkspace/paneState.ts`, which the compiler cannot check
    from here. Naming them once on this side at least makes the pairing greppable, instead
    of leaving eight bare string literals spread across two recipes.
    """

    about = "about"
    edit = "edit"
    preview = "preview"
    split = "split"


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

    """Below `lg`, this view fills the workspace below the app header."""
