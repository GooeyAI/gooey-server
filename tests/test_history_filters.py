from bots.models import SavedRun, Workflow
from widgets.history import _surface_href, _build_surface_tabs
from widgets.surface_filters import (
    ADMIN_ONLY_SURFACES,
    SURFACE_ORDER,
    surface_label,
    visible_surfaces,
)


def test_every_surface_has_a_place_in_the_order():
    # a surface missing from SURFACE_ORDER would silently vanish from the tabs
    assert set(SURFACE_ORDER) == set(SavedRun.Surface)


def test_tabs_read_in_the_order_the_page_wants():
    assert [surface_label(s) for s in visible_surfaces(None)] == [
        "Runs",
        "Deployed Chats",
        "Ask Gooey",
        "Tools",
        "API",
        "Analysis",
        "Bulk",
        "Exports",
    ]


def test_admin_only_surfaces_are_hidden_from_everyone_else():
    assert ADMIN_ONLY_SURFACES == {
        SavedRun.Surface.builder_prompt,
        SavedRun.Surface.internal,
    }
    assert not ADMIN_ONLY_SURFACES & set(visible_surfaces(None))


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
    assert not by_label["Runs"].active
