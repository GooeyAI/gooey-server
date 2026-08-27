from app_users.models import AppUser
from bots.models import SavedRun, Workflow
from widgets.history import (
    _build_owner_options,
    _filterable_workflows,
    _build_surface_tabs,
    _surface_href,
)
from widgets.surface_filters import surface_label, visible_surfaces
from workspaces.models import Workspace


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


def test_a_personal_workspace_has_no_one_else_to_filter_out():
    options = _build_owner_options(
        AppUser(uid="me"),
        Workspace(is_personal=True),
        SavedRun.Surface.run,
        None,
        mine_only=True,
    )

    assert options == []


def test_a_shared_workspace_offers_both_owners():
    options = _build_owner_options(
        AppUser(uid="me"),
        Workspace(name="Acme"),
        SavedRun.Surface.run,
        None,
        mine_only=True,
    )

    assert [o.title for o in options] == ["Just me", "Acme"]


def test_retired_recipes_are_not_offered_as_type_filters():
    workflows = _filterable_workflows(None)

    assert Workflow.VIDEO_BOTS in workflows
    # api-only leftovers, kept off /explore and so off this dropdown too
    assert Workflow.LETTER_WRITER not in workflows
    assert Workflow.SMART_GPT not in workflows


def test_the_filter_you_are_on_names_itself_even_when_retired():
    assert Workflow.LETTER_WRITER in _filterable_workflows(Workflow.LETTER_WRITER)


def test_the_type_filter_is_in_explore_order():
    from daras_ai_v2.all_pages import all_home_pages

    assert _filterable_workflows(None) == [p.workflow for p in all_home_pages]
    # the featured three lead, as they do on /explore
    assert _filterable_workflows(None)[0] == Workflow.VIDEO_BOTS
