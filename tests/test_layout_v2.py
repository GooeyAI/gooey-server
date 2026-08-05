from starlette.testclient import TestClient

from bots.models import SavedRun, Workflow
from daras_ai_v2 import settings
from recipes.VideoBots import VideoBotsPage
from recipes.VideoBots_v2 import VideoBotsPageV2
from routers.root import RecipeTabs
from server import app
from widgets.history import _surface_href, parse_workflow

client = TestClient(app)


def test_video_bots_v2_uses_existing_celery_runner_class():
    assert VideoBotsPageV2.get_runner_page_cls() is VideoBotsPage


def test_layout_v2_run_output_stays_visible_on_mobile():
    page = object.__new__(VideoBotsPageV2)
    page.tab = RecipeTabs.run

    assert page._output_col_class_name() == ""


def test_agent_examples_redirects_to_filtered_explore(
    force_authentication, monkeypatch
):
    monkeypatch.setattr(settings, "ENABLE_LAYOUT_V2", True)

    response = client.get("/agent/examples/", follow_redirects=False)

    assert response.status_code == 301
    assert response.headers["location"].endswith("/explore/?workflow=agent")


def test_agent_history_redirects_to_filtered_global_history(
    force_authentication, monkeypatch
):
    monkeypatch.setattr(settings, "ENABLE_LAYOUT_V2", True)

    response = client.get("/agent/history/", follow_redirects=False)

    assert response.status_code == 301
    assert response.headers["location"].endswith("/history/?workflow=agent")


def test_history_workflow_filter_uses_global_history_url():
    href = _surface_href(SavedRun.Surface.run, Workflow.VIDEO_BOTS)

    assert href == "/history/run/?workflow=agent"


def test_history_workflow_filter_parses_canonical_slug():
    assert parse_workflow("agent") == Workflow.VIDEO_BOTS
    assert parse_workflow("missing") is None
