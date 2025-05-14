import gooey_gui as gui

from bots.models import Workflow
from daras_ai_v2 import icons


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
