import uuid

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from bots.models import PublishedRun, SavedRun, Workflow
from functions.base_llm_tool import render_called_functions
from functions.models import CalledFunction, FunctionTrigger
from gooey_gui.core.renderer import NestingCtx, RenderTreeNode
from gooey_gui.core.state import set_session_state


@pytest.mark.parametrize("n_called", [1, 4])
def test_render_called_functions_costs_one_query_whatever_the_row_count(
    n_called, transactional_db, force_authentication
):
    """Each row's title walks function_run -> parent_version -> published_run, so without
    select_related the pane paid three queries per called function."""
    user = force_authentication
    workspace = user.get_or_create_personal_workspace()[0]
    pr = _make_published_run(user, workspace)
    sr = _make_sr(uid=user.uid, workspace=workspace)
    for _ in range(n_called):
        CalledFunction.objects.create(
            saved_run=sr,
            function_run=_make_sr(
                uid=user.uid,
                workspace=workspace,
                parent_version=pr.versions.first(),
            ),
            trigger=FunctionTrigger.pre.db_value,
        )

    set_session_state({})
    with CaptureQueriesContext(connection) as ctx:
        with NestingCtx(RenderTreeNode("root")):
            render_called_functions(saved_run=sr, trigger=FunctionTrigger.pre)

    assert len(ctx.captured_queries) == 1


def test_render_called_functions_titles_the_rows_from_the_published_run(
    transactional_db, force_authentication
):
    """The title has to survive select_related, not just the query count."""
    user = force_authentication
    workspace = user.get_or_create_personal_workspace()[0]
    pr = _make_published_run(user, workspace)
    sr = _make_sr(uid=user.uid, workspace=workspace)
    CalledFunction.objects.create(
        saved_run=sr,
        function_run=_make_sr(
            uid=user.uid,
            workspace=workspace,
            parent_version=pr.versions.first(),
        ),
        trigger=FunctionTrigger.pre.db_value,
    )

    set_session_state({})
    root = RenderTreeNode("root")
    with NestingCtx(root):
        render_called_functions(saved_run=sr, trigger=FunctionTrigger.pre)

    assert "Test workflow" in str(root.to_dict())


def test_render_called_functions_handles_a_run_with_no_published_parent(
    transactional_db, force_authentication
):
    """`parent_version` is SET_NULL, so select_related has to left-join rather than drop the
    row - and the label falls back to "Function"."""
    user = force_authentication
    workspace = user.get_or_create_personal_workspace()[0]
    sr = _make_sr(uid=user.uid, workspace=workspace)
    CalledFunction.objects.create(
        saved_run=sr,
        function_run=_make_sr(uid=user.uid, workspace=workspace),
        trigger=FunctionTrigger.pre.db_value,
    )

    set_session_state({})
    root = RenderTreeNode("root")
    with CaptureQueriesContext(connection) as ctx:
        with NestingCtx(root):
            render_called_functions(saved_run=sr, trigger=FunctionTrigger.pre)

    assert len(ctx.captured_queries) == 1
    assert "Function" in str(root.to_dict())


def _make_published_run(user, workspace) -> PublishedRun:
    root_sr = _make_sr(
        uid=user.uid,
        workspace=workspace,
        surface=SavedRun.Surface.internal,
    )
    return PublishedRun.objects.create_with_version(
        workflow=Workflow.VIDEO_BOTS,
        published_run_id=uuid.uuid4().hex[:12],
        saved_run=root_sr,
        user=user,
        workspace=workspace,
        title="Test workflow",
    )


def _make_sr(**kwargs) -> SavedRun:
    kwargs.setdefault("workflow", Workflow.VIDEO_BOTS)
    kwargs.setdefault("run_id", uuid.uuid4().hex)
    return SavedRun.objects.create(**kwargs)
