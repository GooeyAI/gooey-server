from __future__ import annotations

import datetime
from enum import Enum

import gooey_gui as gui
from typing_extensions import NotRequired, TypedDict

from daras_ai_v2.base import BasePage, RecipeRunState, StateKeys
from widgets.bulk_progress_state import (
    BulkEvalProgress,
    BulkProgress,
    is_bulk_progress_complete,
)

BULK_RERUN_ALL_KEY = "-submit-workflow"


class BulkRunnerRunState(str, Enum):
    running = "running"
    stopping = "stopping"
    evaluating = "evaluating"
    complete = "complete"
    error = "error"
    stopped = "stopped"


# Keep in sync with gooey-gui/app/components/bulkProgress/bulkProgress.types.ts (BulkProgressSnapshot).
class BulkProgressSnapshot(TypedDict, total=False):
    runState: BulkRunnerRunState
    elapsedSeconds: float | None
    completedUnitRuns: int
    totalUnitRuns: int
    totalRows: int
    currentRowNumber: int
    currentWorkflowNumber: int
    totalWorkflows: int
    currentWorkflowTitle: str
    currentWorkflowUrl: str
    currentWorkflowRunTimeSeconds: NotRequired[float | None]
    creditsUsed: NotRequired[int]
    totalEvalRuns: NotRequired[int]
    evalCurrent: NotRequired[int]
    evalTotal: NotRequired[int]
    evalWorkflowTitle: NotRequired[str]
    inputPrompt: NotRequired[str]
    inputAudioUrl: NotRequired[str]
    lastCompletedWorkflowTitle: NotRequired[str]
    lastCompletedWorkflowUrl: NotRequired[str]
    lastCompletedRunTimeSeconds: NotRequired[float | None]
    lastCompletedCredits: NotRequired[int | None]


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

    gui.component(
        "BulkProgressCard",
        snapshot=snapshot,
        rerunAllKey=BULK_RERUN_ALL_KEY,
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

    snapshot: BulkProgressSnapshot = {
        "runState": run_state,
        "elapsedSeconds": elapsed_seconds,
        "completedUnitRuns": progress["completed_unit_runs"],
        "totalUnitRuns": progress["total_unit_runs"],
        "totalRows": progress["total_rows"],
        "currentRowNumber": progress["current_row_number"],
        "currentWorkflowNumber": progress["current_workflow_number"],
        "totalWorkflows": progress["total_workflows"],
        "currentWorkflowTitle": progress["workflow_title"],
        "currentWorkflowUrl": progress["workflow_url"],
    }
    if "workflow_run_time_seconds" in progress:
        snapshot["currentWorkflowRunTimeSeconds"] = progress[
            "workflow_run_time_seconds"
        ]
    if "credits_used" in progress:
        snapshot["creditsUsed"] = progress["credits_used"]
    if "total_eval_runs" in progress:
        snapshot["totalEvalRuns"] = progress["total_eval_runs"]
    if run_state == BulkRunnerRunState.evaluating and eval_progress:
        snapshot["evalCurrent"] = eval_progress["current"]
        snapshot["evalTotal"] = eval_progress["total"]
        snapshot["evalWorkflowTitle"] = eval_progress["workflow_title"]
    if input_prompt := progress.get("input_prompt"):
        snapshot["inputPrompt"] = input_prompt
    if input_audio := progress.get("input_audio"):
        snapshot["inputAudioUrl"] = input_audio
    if progress.get("last_completed_workflow_title") and progress.get(
        "last_completed_workflow_url"
    ):
        snapshot["lastCompletedWorkflowTitle"] = progress[
            "last_completed_workflow_title"
        ]
        snapshot["lastCompletedWorkflowUrl"] = progress["last_completed_workflow_url"]
        if "last_completed_run_time_seconds" in progress:
            snapshot["lastCompletedRunTimeSeconds"] = progress[
                "last_completed_run_time_seconds"
            ]
        if "last_completed_credits" in progress:
            snapshot["lastCompletedCredits"] = progress["last_completed_credits"]
    return snapshot


def bulk_snapshot_run_state(
    *,
    progress: BulkProgress,
    is_cancelled: bool,
    recipe_run_state: RecipeRunState,
) -> BulkRunnerRunState | None:
    is_active = recipe_run_state in {RecipeRunState.starting, RecipeRunState.running}
    if is_active and is_cancelled:
        return BulkRunnerRunState.stopping

    if recipe_run_state == RecipeRunState.failed:
        return BulkRunnerRunState.error

    bulk_complete = is_bulk_progress_complete(progress)
    if not bulk_complete:
        if is_active:
            return BulkRunnerRunState.running
        return BulkRunnerRunState.stopped

    if progress["phase"] == "evaluating":
        return BulkRunnerRunState.evaluating

    return BulkRunnerRunState.complete
