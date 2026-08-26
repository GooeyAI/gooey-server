from __future__ import annotations

from enum import Enum

import pydantic


# `(str, Enum)` rather than `enum.StrEnum`: this runs on 3.10, where StrEnum does not exist.
class RecipeView(str, Enum):
    """The client-side views of the layout-v2 workspace.

    Defined here, in the props package, because these ids cross into TypeScript: the
    generator emits them as a named `RecipeView` union in every `.d.ts` that references
    them, and `RecipeWorkspace/paneState.ts` imports that instead of declaring its own.
    One definition, checked by the compiler on the far side.

    `daras_ai_v2.tab_spec` re-exports this, so recipes keep importing it from there.
    """

    about = "about"
    edit = "edit"
    preview = "preview"
    split = "split"


class WorkPane(str, Enum):
    """One of the two work surfaces, as opposed to one of the views.

    Not a `RecipeView`: these name panes, and only the preview is both. Defined here for
    the same reason - `RecipeWorkspace/paneState.ts` imports the generated union rather
    than declaring its own.
    """

    editor = "editor"
    preview = "preview"


class RecipeWorkspaceProps(pydantic.BaseModel):
    """The workspace shell: three server-rendered surfaces, arranged by the client.

    Takes About, the editor and the preview as its render-tree children, in that order,
    and decides which are on screen and how wide. Switching view costs no round trip,
    which is the whole point - the trade is that all three render every request.
    """

    _component: str = "RecipeWorkspace"

    # sessionStorage key holding this run's chosen layout. Shared with RecipeTopBar and
    # every RecipeWorkspaceTrigger on the page - all three must name the same key or they
    # arrange independently.
    storage_key: str
    # Where this workflow opens when the session has chosen nothing yet.
    initial_view: RecipeView
    # An open config pane has asked for the whole row, so the preview is dropped from what
    # is shown without touching the layout stored behind it. See `shownLayout`.
    editor_full_width: bool = False
    # Which half of a two-pane view a phone shows. There is room for one below lg, and which
    # one is the recipe's call - see `BasePage.narrow_pane`.
    narrow_pane: WorkPane = WorkPane.preview


class RecipeWorkspaceTriggerProps(pydantic.BaseModel):
    """A button that selects a view, and optionally a pane within it.

    Wraps its children, so the caller supplies the whole visual - About's meta cards are
    the only user today. `state_key`/`state_value` are the pane half: the client writes
    them and notifies, which is what lets a card on About land on a specific config pane.
    """

    _component: str = "RecipeWorkspaceTrigger"

    storage_key: str
    initial_view: RecipeView
    # The view to select. Not `RecipeView | None`: a trigger that selects nothing has no
    # reason to exist.
    view: RecipeView
    # Session-state key to write on click, and the value to write. Empty key means the
    # trigger only changes view. The value is a plain string because it is a pane id -
    # recipes pass their own str enum, which serialises to exactly that.
    state_key: str = ""
    state_value: str = ""
    className: str = ""


class WorkspacePaneControlProps(pydantic.BaseModel):
    """A square icon button, or a labelled pill, pinned to a pane's corner.

    Used for the pane-pairing controls the workspace renders itself, and for the Builder
    panel's own close and title buttons.
    """

    _component: str = "WorkspacePaneControl"

    label: str
    # Hover text, when it says something the label does not. A labelled control names a
    # surface ("Ask Gooey"); its tooltip can name the action ("New Chat"). Falls back to
    # `label`, which is all an icon-only control needs.
    tooltip: str = ""
    # A bare FontAwesome class, NOT html - this component builds the `<i>` itself. See
    # `icons.cls`. Ignored when `photo_url` is set.
    icon: str = ""
    # Renders a logo in place of the icon, for a control that identifies a surface.
    photo_url: str = ""
    # Show `label` beside the icon, turning the square button into a pill.
    show_label: bool = False
    # A `window` event to dispatch on click. The pane-pairing controls pass none - they are
    # rendered by RecipeWorkspace, which hands them a React `onClick` directly.
    event_name: str = ""
    className: str = ""


class GooeyEmbedTeardownProps(pydantic.BaseModel):
    """Removes the stranded chat-preview widget when its pane goes away.

    Renders nothing; it exists only for the unmount hook. `embed_key` identifies the
    workflow whose widget this is, so React tears down and remounts when it changes rather
    than leaving the previous run's preview on screen.
    """

    _component: str = "GooeyEmbedTeardown"

    embed_key: str
