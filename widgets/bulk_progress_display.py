from __future__ import annotations

import datetime

import gooey_gui as gui

from daras_ai_v2.base import BasePage, RecipeRunState, StateKeys
from gooey_gui.types.bulk_progress_props import (
    BulkProgressCardProps,
    BulkProgressSnapshot,
    BulkRunnerRunState,
)
from widgets.bulk_progress_state import (
    BulkEvalProgress,
    BulkProgress,
    is_bulk_progress_complete,
)


def render_bulk_runner_progress(*, is_cancelled: bool) -> None:
    session = gui.session_state
    progress = session.get("bulk_progress")
    if not progress:
        return

    run_time = session.get(StateKeys.run_time)
    elapsed_seconds = None
    if run_time is not None:
        if isinstance(run_time, datetime.timedelta):
            elapsed_seconds = run_time.total_seconds()
        else:
            elapsed_seconds = run_time

    snapshot = build_bulk_progress_snapshot(
        progress=progress,
        is_cancelled=is_cancelled,
        recipe_run_state=BasePage.get_run_state(session),
        elapsed_seconds=elapsed_seconds,
        eval_progress=session.get("eval_progress"),
    )
    if not snapshot:
        return

    props = BulkProgressCardProps(
        snapshot=snapshot,
        rerunAllKey="-submit-workflow",
    )
    gui.component(
        "BulkProgressCard",
        **props.model_dump(mode="json", exclude_none=True),
    )


def build_bulk_progress_snapshot(
    *,
    progress: BulkProgress,
    is_cancelled: bool,
    recipe_run_state: RecipeRunState,
    elapsed_seconds: float | None,
    eval_progress: BulkEvalProgress | None = None,
) -> BulkProgressSnapshot | None:
    run_state = bulk_snapshot_run_state(
        progress=progress,
        is_cancelled=is_cancelled,
        recipe_run_state=recipe_run_state,
    )
    if not run_state:
        return None

    eval_current = None
    eval_total = None
    eval_workflow_title = None
    if run_state == BulkRunnerRunState.evaluating and eval_progress:
        eval_current = eval_progress["current"]
        eval_total = eval_progress["total"]
        eval_workflow_title = eval_progress["workflow_title"]

    last_completed_workflow_title = None
    last_completed_workflow_url = None
    last_completed_run_time_seconds = None
    last_completed_credits = None
    if progress.get("last_completed_workflow_title") and progress.get(
        "last_completed_workflow_url"
    ):
        last_completed_workflow_title = progress["last_completed_workflow_title"]
        last_completed_workflow_url = progress["last_completed_workflow_url"]
        last_completed_run_time_seconds = progress.get(
            "last_completed_run_time_seconds"
        )
        last_completed_credits = progress.get("last_completed_credits")

    return BulkProgressSnapshot(
        runState=run_state,
        elapsedSeconds=elapsed_seconds,
        completedUnitRuns=progress["completed_unit_runs"],
        totalUnitRuns=progress["total_unit_runs"],
        totalRows=progress["total_rows"],
        currentRowNumber=progress["current_row_number"],
        currentWorkflowNumber=progress["current_workflow_number"],
        totalWorkflows=progress["total_workflows"],
        currentWorkflowTitle=progress["workflow_title"],
        currentWorkflowUrl=progress["workflow_url"],
        currentWorkflowRunTimeSeconds=progress.get("workflow_run_time_seconds"),
        creditsUsed=progress.get("credits_used"),
        totalEvalRuns=progress.get("total_eval_runs"),
        evalCurrent=eval_current,
        evalTotal=eval_total,
        evalWorkflowTitle=eval_workflow_title,
        inputPrompt=progress.get("input_prompt") or None,
        inputAudioUrl=progress.get("input_audio") or None,
        lastCompletedWorkflowTitle=last_completed_workflow_title,
        lastCompletedWorkflowUrl=last_completed_workflow_url,
        lastCompletedRunTimeSeconds=last_completed_run_time_seconds,
        lastCompletedCredits=last_completed_credits,
    )


def bulk_snapshot_run_state(
    *,
    progress: BulkProgress,
    is_cancelled: bool,
    recipe_run_state: RecipeRunState,
) -> BulkRunnerRunState | None:
    is_active = recipe_run_state in {RecipeRunState.starting, RecipeRunState.running}

    if is_cancelled:
        if is_active:
            return BulkRunnerRunState.stopping
        return BulkRunnerRunState.stopped

    if recipe_run_state == RecipeRunState.failed:
        return BulkRunnerRunState.error

    if is_active:
        if progress["phase"] == "evaluating":
            return BulkRunnerRunState.evaluating
        return BulkRunnerRunState.running

    if is_bulk_progress_complete(progress):
        return BulkRunnerRunState.complete

    return BulkRunnerRunState.stopped
