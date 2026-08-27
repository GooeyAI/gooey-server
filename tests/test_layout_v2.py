from gooey_gui.types.recipe_workspace_props import WorkPane
from recipes.VideoBots import VideoBotsPage
from recipes.VideoBots_v2 import VideoBotsPageV2
from routers.root import RecipeTabs


def test_video_bots_v2_uses_existing_celery_runner_class():
    assert VideoBotsPageV2.get_runner_page_cls() is VideoBotsPage


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
