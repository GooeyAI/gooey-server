from types import SimpleNamespace

from daras_ai_v2.base import BasePage as BasePageV1
from gooey_gui.types.recipe_workspace_props import WorkPane
from recipes.VideoBots import VideoBotsPage
from recipes.VideoBots_v2 import VideoBotsPageV2
from routers.root import RecipeTabs


def test_video_bots_v2_uses_existing_celery_runner_class():
    assert VideoBotsPageV2.get_runner_page_cls() is VideoBotsPage


def test_video_bots_v2_inherits_business_logic():
    assert VideoBotsPageV2.create_new_run is VideoBotsPage.create_new_run
    assert VideoBotsPageV2.run_v2 is VideoBotsPage.run_v2
    assert VideoBotsPageV2.bind_tool is BasePageV1.bind_tool
    assert VideoBotsPageV2.render_steps is VideoBotsPage.render_steps


def test_layout_v2_run_output_stays_visible_on_mobile():
    page = object.__new__(VideoBotsPageV2)
    page.tab = RecipeTabs.run

    assert page._output_col_class_name() == ""


def test_narrow_pane_keeps_the_editor_for_a_visitor(monkeypatch):
    """A visitor's one work tab is "How it works", which exists to show the configuration -
    so a phone keeps the editor. An owner on Split keeps the bot."""
    page = object.__new__(VideoBotsPageV2)

    monkeypatch.setattr(VideoBotsPageV2, "is_unowned_example", lambda self: True)
    assert page.narrow_pane() == WorkPane.editor

    monkeypatch.setattr(VideoBotsPageV2, "is_unowned_example", lambda self: False)
    assert page.narrow_pane() == WorkPane.preview


def test_title_menu_offers_v1s_options(monkeypatch):
    """The chevron menu is v1's Options dialog, gated the same way."""
    from bots.models import WorkflowAccessLevel

    page = object.__new__(VideoBotsPageV2)
    pr = SimpleNamespace(
        is_root=lambda: False, saved_run="sr", tags=SimpleNamespace(all=list)
    )
    monkeypatch.setattr(VideoBotsPageV2, "is_logged_in", lambda self: True)
    monkeypatch.setattr(VideoBotsPageV2, "current_pr", property(lambda self: pr))
    monkeypatch.setattr(VideoBotsPageV2, "current_sr", property(lambda self: "sr"))
    monkeypatch.setattr(
        VideoBotsPageV2, "current_workspace", property(lambda self: None)
    )
    monkeypatch.setattr(
        WorkflowAccessLevel, "can_user_delete_published_run", lambda **kw: True
    )
    page.request = SimpleNamespace(user=object())

    labels = [item.label for item in page._title_menu_items()]
    assert labels == ["Version history", "Duplicate", "Delete"]

    # off an older version, duplicating means promoting that version to a new workflow
    monkeypatch.setattr(VideoBotsPageV2, "current_sr", property(lambda self: "older"))
    assert [i.label for i in page._title_menu_items()][1] == "Save as New"


def test_title_menu_is_empty_when_logged_out(monkeypatch):
    page = object.__new__(VideoBotsPageV2)
    monkeypatch.setattr(VideoBotsPageV2, "is_logged_in", lambda self: False)
    assert page._title_menu_items() == []
