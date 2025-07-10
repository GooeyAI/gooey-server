import gooey_gui as gui

from bots.models import Workflow
from daras_ai_v2 import icons
from widgets.author import (
    render_author_as_breadcrumb,
)
from app_users.models import AppUser
from daras_ai_v2.breadcrumbs import render_breadcrumbs
from bots.models import (
    PublishedRun,
    SavedRun,
)
from workspaces.models import Workspace


def render_help_button(workflow: Workflow):
    meta = workflow.get_or_create_metadata()
    if not meta.help_url:
        return

    with (
        gui.link(to=meta.help_url, target="_blank"),
        gui.tag(
            "button",
            type="button",
            className="btn btn-theme btn-tertiary m-0",
        ),
    ):
        gui.html(
            f'{icons.help_guide} <span class="text-muted d-none d-lg-inline">Help Guide</span>'
        )


def render_breadcrumbs_with_author(
    tbreadcrumbs,
    *,
    is_root_example: bool = False,
    user: AppUser | None = None,
    pr: PublishedRun | None = None,
    sr: SavedRun | None = None,
    current_workspace: Workspace | None = None,
):
    with gui.div(
        className="d-flex flex-wrap align-items-center container-margin-reset"
    ):
        with gui.div(className="me-2"):
            render_breadcrumbs(tbreadcrumbs)
        if not is_root_example:
            with gui.div(className="d-flex align-items-center"):
                gui.write("by", className="me-2 d-none d-md-block text-muted")
                render_author_as_breadcrumb(
                    user=user,
                    pr=pr,
                    sr=sr,
                    current_workspace=current_workspace,
                )
