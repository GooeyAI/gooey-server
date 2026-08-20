from unittest.mock import MagicMock

from starlette.testclient import TestClient

from bots.models import SavedRun, Workflow, get_default_published_run_workspace
from daras_ai_v2 import settings
from recipes.VideoBots import VideoBotsPage
from recipes.VideoBots_v2 import VideoBotsPageV2
from routers.api import create_new_run
from routers.root import RecipeTabs
from server import app
from widgets.history import _surface_href, parse_workflow
from workspaces.models import Workspace

client = TestClient(app)


def test_video_bots_v2_uses_existing_celery_runner_class():
    assert VideoBotsPageV2.get_runner_page_cls() is VideoBotsPage


def test_video_bots_v2_reuses_v1_request_and_response_models():
    assert "run_v2" not in VideoBotsPageV2.__dict__
    assert "llm_loop" not in VideoBotsPageV2.__dict__
    assert VideoBotsPageV2.RequestModel is VideoBotsPage.RequestModel
    assert VideoBotsPageV2.ResponseModel is VideoBotsPage.ResponseModel


def test_video_bots_v2_call_runner_task_pickles_v1_class(monkeypatch):
    captured = {}

    class _Result:
        id = "task-1"

    def _delay(**kwargs):
        captured.update(kwargs)
        return _Result()

    monkeypatch.setattr("celeryapp.tasks.runner_task.delay", _delay)

    page = object.__new__(VideoBotsPageV2)
    page.request = MagicMock()
    page.request.user.id = 1
    sr = MagicMock()
    sr.run_id = "run-1"
    sr.uid = "uid-1"

    page.call_runner_task(sr)

    assert captured["page_cls"] is VideoBotsPage
    assert captured["run_id"] == "run-1"
    assert sr.celery_task_id == "task-1"
    sr.save.assert_called_once()


def test_video_bots_v2_enqueues_v1_page_class(
    db_fixtures, force_authentication, monkeypatch
):
    captured = {}

    class _Result:
        id = "task-1"

    def _delay(**kwargs):
        captured.update(kwargs)
        return _Result()

    monkeypatch.setattr("celeryapp.tasks.runner_task.delay", _delay)

    user = force_authentication
    workspace = Workspace.objects.get(id=get_default_published_run_workspace())
    page, sr = create_new_run(
        page_cls=VideoBotsPageV2,
        query_params={},
        current_user=user,
        workspace=workspace,
        request_body=_video_bots_request_body(input_prompt="run me"),
    )
    page.call_runner_task(sr)

    assert captured["page_cls"] is VideoBotsPage
    assert captured["run_id"] == sr.run_id
    assert sr.celery_task_id == "task-1"


def test_video_bots_v2_create_new_run_schedules_conversation_title(
    db_fixtures, force_authentication, monkeypatch
):
    called = []
    monkeypatch.setattr(
        "recipes.VideoBots_v2.run_conversation_title_generator",
        lambda sr, user: called.append((sr.id, user.id)),
    )

    user = force_authentication
    workspace = Workspace.objects.get(id=get_default_published_run_workspace())
    _, sr = create_new_run(
        page_cls=VideoBotsPageV2,
        query_params={},
        current_user=user,
        workspace=workspace,
        request_body=_video_bots_request_body(input_prompt="first message"),
    )
    sr.refresh_from_db()

    assert sr.message_thread_id
    assert sr.message_thread.title == "first message"
    assert called == [(sr.id, user.id)]


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


def _video_bots_request_body(*, input_prompt: str) -> dict:
    state = VideoBotsPage.get_root_pr().saved_run.state.copy()
    request_body = VideoBotsPage.get_example_request(state)[1].copy()
    request_body["input_prompt"] = input_prompt
    return request_body
