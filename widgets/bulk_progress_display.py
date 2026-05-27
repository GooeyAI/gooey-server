from __future__ import annotations

import datetime
from typing import Literal

import gooey_gui as gui
from typing_extensions import NotRequired, TypedDict

from daras_ai_v2.base import StateKeys
from widgets.bulk_progress_state import (
    BulkEvalProgress,
    BulkProgress,
    coerce_seconds,
    is_bulk_progress_complete,
)

BULK_RERUN_ALL_KEY = "-submit-workflow"

BulkRunnerRunState = Literal[
    "running", "stopping", "evaluating", "complete", "error", "stopped"
]


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
    evalCurrent: NotRequired[int]
    evalTotal: NotRequired[int]
    evalWorkflowTitle: NotRequired[str]
    inputPrompt: NotRequired[str]
    inputAudioUrl: NotRequired[str]
    lastCompletedWorkflowTitle: NotRequired[str]
    lastCompletedWorkflowUrl: NotRequired[str]
    lastCompletedRunTimeSeconds: NotRequired[float | None]
    lastCompletedCredits: NotRequired[int | None]


def get_bulk_runner_run_state(
    *,
    progress: BulkProgress | None,
    is_cancelled: bool,
    is_running: bool,
    error_msg: str | None,
) -> BulkRunnerRunState | None:
    if not progress:
        return None

    bulk_complete = is_bulk_progress_complete(progress)

    if is_running and is_cancelled:
        return "stopping"

    if is_running and bulk_complete:
        if progress["phase"] == "evaluating":
            return progress["phase"]
        return "complete"

    if is_running:
        return "running"

    if error_msg:
        return "error"

    if bulk_complete and not is_running:
        return "complete"

    return "stopped"


def get_bulk_elapsed_seconds(
    *,
    is_running: bool,
    run_time: float | datetime.timedelta | None,
    created_at: datetime.datetime | str | None,
) -> float | None:
    seconds = coerce_seconds(run_time)
    if seconds is not None:
        return seconds

    if not is_running or not created_at:
        return None

    if isinstance(created_at, str):
        created_at = datetime.datetime.fromisoformat(created_at)
    now = datetime.datetime.now(created_at.tzinfo)
    return max((now - created_at).total_seconds(), 0)


def render_bulk_runner_progress(*, is_cancelled: bool) -> None:
    session = gui.session_state
    progress = session.get("bulk_progress")
    is_running = bool(session.get(StateKeys.run_status))
    error_msg = session.get(StateKeys.error_msg)
    run_state = get_bulk_runner_run_state(
        progress=progress,
        is_cancelled=is_cancelled,
        is_running=is_running,
        error_msg=error_msg,
    )
    if not progress or not run_state:
        return

    elapsed_seconds = get_bulk_elapsed_seconds(
        is_running=is_running,
        run_time=session.get(StateKeys.run_time),
        created_at=session.get(StateKeys.created_at),
    )
    snapshot = build_bulk_progress_snapshot(
        progress=progress,
        run_state=run_state,
        elapsed_seconds=elapsed_seconds,
        eval_progress=session.get("eval_progress")
        if run_state == "evaluating"
        else None,
    )
    gui.component(
        "BulkProgressCard",
        snapshot=snapshot,
        rerunAllKey=BULK_RERUN_ALL_KEY,
    )


def build_bulk_progress_snapshot(
    *,
    progress: BulkProgress,
    run_state: BulkRunnerRunState,
    elapsed_seconds: float | None,
    eval_progress: BulkEvalProgress | None = None,
) -> BulkProgressSnapshot:
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
    if eval_progress:
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
