from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel

BulkProgressPhase = Literal["running", "evaluating", "complete"]


class BulkRunnerRunState(str, Enum):
    running = "running"
    stopping = "stopping"
    evaluating = "evaluating"
    complete = "complete"
    error = "error"
    stopped = "stopped"


class BulkEvalProgress(BaseModel):
    current: int
    total: int
    workflow_title: str


class BulkProgressUnitCounts(BaseModel):
    completed_unit_runs: int = 0
    total_unit_runs: int = 0
    total_rows: int = 0
    current_row_number: int = 0
    current_workflow_number: int = 1
    total_workflows: int = 0


class BulkProgressCounts(BulkProgressUnitCounts):
    completed_row_groups: int = 0
    total_row_groups: int = 0
    completed_rows: int = 0


class BulkProgressCompletionInfo(BaseModel):
    credits_used: int | None = None
    total_eval_runs: int | None = None
    last_completed_workflow_title: str | None = None
    last_completed_workflow_url: str | None = None
    last_completed_run_time_seconds: float | None = None
    last_completed_credits: int | None = None
    workflow_title: str = ""
    workflow_url: str = ""
    input_prompt: str = ""
    input_audio: str | None = None
    workflow_run_time_seconds: float | None = None


class BulkProgress(BulkProgressCounts, BulkProgressCompletionInfo):
    phase: BulkProgressPhase = "running"
    workflow_credits: int | None = None
    error_msg: str | None = None


class BulkProgressSnapshot(BulkProgressUnitCounts, BulkProgressCompletionInfo):
    run_state: BulkRunnerRunState
    elapsed_seconds: float | None = None

    eval_current: int | None = None
    eval_total: int | None = None
    eval_workflow_title: str | None = None

    @classmethod
    def from_bulk_progress(
        cls,
        *,
        progress: BulkProgress,
        run_state: BulkRunnerRunState,
        elapsed_seconds: float | None,
        eval_progress: BulkEvalProgress | None = None,
    ) -> BulkProgressSnapshot:
        shared_field_names = {
            *BulkProgressUnitCounts.model_fields.keys(),
            *BulkProgressCompletionInfo.model_fields.keys(),
        }
        snapshot = cls(
            **progress.model_dump(include=shared_field_names),
            run_state=run_state,
            elapsed_seconds=elapsed_seconds,
        )
        if run_state == BulkRunnerRunState.evaluating and eval_progress:
            snapshot.eval_current = eval_progress.current
            snapshot.eval_total = eval_progress.total
            snapshot.eval_workflow_title = eval_progress.workflow_title
        return snapshot


class BulkProgressCardProps(BaseModel):
    _component: str = "BulkProgressCard"

    snapshot: BulkProgressSnapshot
    rerun_all_key: str | None = None
