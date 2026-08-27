from bots.models import SavedRun, Workflow
from widgets.history import _build_surface_tabs, _surface_href
from widgets.surface_filters import surface_label, visible_surfaces


def test_admin_only_surfaces_are_hidden_from_everyone_else():
    labels = [surface_label(s) for s in visible_surfaces(None)]

    assert labels == [
        "Runs",
        "Deployed Chats",
        "Ask Gooey",
        "Tools",
        "API",
        "Analysis",
        "Bulk",
        "Exports",
    ]
    assert "Internal" not in labels


def test_just_me_is_the_default_so_it_needs_no_param():
    assert _surface_href(SavedRun.Surface.run, mine_only=True) == "/history/run/"


def test_switching_surface_keeps_the_other_filters():
    tabs = _build_surface_tabs(
        SavedRun.Surface.deployment,
        visible_surfaces(None),
        Workflow.VIDEO_BOTS,
        mine_only=False,
    )
    by_label = {t.title: t for t in tabs}

    assert by_label["Runs"].href == "/history/run/?workflow=agent&for=all"
    assert by_label["Deployed Chats"].active
