from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import gooey_gui as gui
from bots.models import PublishedRun, Workflow, WorkflowAccessLevel
from recipes.VideoBots_v2 import VideoBotsPageV2


@pytest.mark.parametrize("can_edit", [True, False])
@pytest.mark.parametrize("is_latest_version", [True, False])
def test_duplicate_workflow_is_private(monkeypatch, can_edit, is_latest_version):
    saved_run = object()
    current_run = saved_run if is_latest_version else object()
    pr = SimpleNamespace(
        workflow=Workflow.VIDEO_BOTS,
        saved_run=saved_run,
        title="Public workflow",
        notes="Description",
        public_access=WorkflowAccessLevel.FIND_AND_VIEW,
        tags=SimpleNamespace(all=list),
        is_root=lambda: False,
    )
    pr.duplicate = lambda **kwargs: PublishedRun.duplicate(pr, **kwargs)
    workspace = SimpleNamespace(
        should_default_runs_be_public=lambda: True,
        can_have_private_published_runs=lambda: False,
    )
    page = object.__new__(VideoBotsPageV2)
    page.request = SimpleNamespace(
        user=SimpleNamespace(first_name_possesive=lambda: "User's")
    )
    monkeypatch.setattr(VideoBotsPageV2, "current_pr", property(lambda self: pr))
    monkeypatch.setattr(
        VideoBotsPageV2, "current_sr", property(lambda self: current_run)
    )
    monkeypatch.setattr(
        VideoBotsPageV2, "current_workspace", property(lambda self: workspace)
    )
    monkeypatch.setattr(
        WorkflowAccessLevel, "can_user_edit_published_run", lambda **kwargs: can_edit
    )
    create = Mock(return_value=SimpleNamespace(published_run_id="copy"))
    monkeypatch.setattr(PublishedRun.objects, "create_with_version", create)
    page.app_url = lambda **kwargs: "/copy/"

    with pytest.raises(gui.RedirectException):
        page._duplicate_and_redirect()

    assert create.call_args.kwargs["public_access"] == WorkflowAccessLevel.VIEW_ONLY
    assert create.call_args.kwargs["saved_run"] is (
        current_run if can_edit else saved_run
    )
    assert pr.public_access == WorkflowAccessLevel.FIND_AND_VIEW
