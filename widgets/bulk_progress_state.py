from __future__ import annotations

from typing import Literal

from typing_extensions import NotRequired, TypedDict

from bots.models import SavedRun
from daras_ai_v2.base import BasePage
from daras_ai_v2.breadcrumbs import get_title_breadcrumbs

BulkProgressPhase = Literal["running", "evaluating", "complete"]
BULK_INPUT_PROMPT_PREVIEW_CHARS = 160


class BulkEvalProgress(TypedDict):
    current: int
    total: int
    workflow_title: str


class BulkProgressCounts(TypedDict):
    completed_unit_runs: int
    total_unit_runs: int
    completed_row_groups: int
    total_row_groups: int
    completed_rows: int
    total_rows: int
    current_row_number: int
    current_workflow_number: int
    total_workflows: int


class BulkProgress(BulkProgressCounts):
    phase: BulkProgressPhase
    workflow_title: str
    workflow_url: str
    input_prompt: str
    input_audio: NotRequired[str]
    credits_used: NotRequired[int]
    workflow_run_time_seconds: NotRequired[float]
    workflow_credits: NotRequired[int]
    total_eval_runs: NotRequired[int]
    last_completed_workflow_title: NotRequired[str]
    last_completed_workflow_url: NotRequired[str]
    last_completed_run_time_seconds: NotRequired[float]
    last_completed_credits: NotRequired[int]
    error_msg: NotRequired[str]


class BulkProgressTracker:
    def __init__(
        self,
        *,
        total_rows: int,
        total_row_groups: int,
        total_workflows: int,
    ):
        self.counts: BulkProgressCounts = {
            "completed_unit_runs": 0,
            "total_unit_runs": total_row_groups * total_workflows,
            "completed_row_groups": 0,
            "total_row_groups": total_row_groups,
            "completed_rows": 0,
            "total_rows": total_rows,
            "current_row_number": 0,
            "current_workflow_number": 1,
            "total_workflows": total_workflows,
        }
        self.credits_used = 0
        self.snapshot: BulkProgress | None = None

    def workflow_started(
        self,
        response,
        *,
        current_row_number: int,
        workflow_number: int,
        page_cls: type[BasePage],
        sr: SavedRun,
        pr,
        request_body: dict,
    ) -> str:
        self.counts.update(
            current_row_number=current_row_number,
            current_workflow_number=workflow_number,
        )
        return self._emit_bulk_progress(
            response,
            page_cls=page_cls,
            sr=sr,
            pr=pr,
            request_body=request_body,
            phase="running",
            current_workflow_completed=False,
        )

    def workflow_completed(
        self,
        response,
        *,
        page_cls: type[BasePage],
        sr: SavedRun,
        pr,
        request_body: dict,
        arr_len: int,
        workflow_run_time_seconds: float | None,
        workflow_credits: int | None,
        error_msg: str | None,
    ) -> str:
        self.counts["completed_unit_runs"] += 1
        if self.counts["current_workflow_number"] == self.counts["total_workflows"]:
            self.counts["completed_row_groups"] += 1
            self.counts["completed_rows"] += arr_len
        self.credits_used += workflow_credits or 0

        return self._emit_bulk_progress(
            response,
            page_cls=page_cls,
            sr=sr,
            pr=pr,
            request_body=request_body,
            phase="running",
            credits_used=self.credits_used,
            workflow_run_time_seconds=workflow_run_time_seconds,
            workflow_credits=workflow_credits,
            error_msg=error_msg,
        )

    def eval_started(
        self,
        response,
        *,
        current: int,
        total: int,
        workflow_title: str,
    ) -> str:
        response.eval_progress = {
            "current": current,
            "total": total,
            "workflow_title": workflow_title,
        }
        if self.snapshot:
            self.snapshot["phase"] = "evaluating"
            self.snapshot["total_eval_runs"] = total
            response.bulk_progress = self.snapshot
        return f"Running {workflow_title}..."

    def eval_completed(
        self,
        response,
        *,
        eval_credits: int | None,
    ) -> str | None:
        self.credits_used += eval_credits or 0
        if not self.snapshot:
            return None

        self.snapshot["credits_used"] = self.credits_used
        response.bulk_progress = self.snapshot
        return f"{bulk_progress_percent(self.snapshot)}% Completed"

    def evals_completed(self, response) -> None:
        response.eval_progress = None
        if self.snapshot:
            self.snapshot["phase"] = "complete"
            response.bulk_progress = self.snapshot

    def _emit_bulk_progress(
        self,
        response,
        *,
        page_cls: type[BasePage],
        sr: SavedRun,
        pr,
        request_body: dict,
        phase: BulkProgressPhase,
        current_workflow_completed: bool = True,
        credits_used: int | None = None,
        workflow_run_time_seconds: float | None = None,
        workflow_credits: int | None = None,
        error_msg: str | None = None,
    ) -> str:
        self.snapshot = build_bulk_progress(
            progress=self.counts,
            page_cls=page_cls,
            sr=sr,
            pr=pr,
            request_body=request_body,
            phase=phase,
            previous_progress=self.snapshot,
            credits_used=credits_used,
            workflow_run_time_seconds=workflow_run_time_seconds,
            workflow_credits=workflow_credits,
            error_msg=error_msg,
            current_workflow_completed=current_workflow_completed,
        )
        response.bulk_progress = self.snapshot

        return f"{bulk_progress_percent(self.snapshot)}% Completed"


def is_bulk_progress_complete(progress: BulkProgressCounts) -> bool:
    total_unit_runs = progress["total_unit_runs"]
    return total_unit_runs > 0 and progress["completed_unit_runs"] >= total_unit_runs


def build_bulk_progress(
    *,
    progress: BulkProgressCounts,
    page_cls: type[BasePage],
    sr: SavedRun,
    pr,
    request_body: dict,
    phase: BulkProgressPhase,
    previous_progress: BulkProgress | None = None,
    credits_used: int | None = None,
    workflow_run_time_seconds: float | None = None,
    workflow_credits: int | None = None,
    error_msg: str | None = None,
    current_workflow_completed: bool = True,
) -> BulkProgress:
    title = get_title_breadcrumbs(page_cls=page_cls, sr=sr, pr=pr).title_with_prefix()
    input_prompt = page_cls.preview_input(request_body)
    bulk_progress: BulkProgress = {
        **progress,
        "phase": phase,
        "workflow_title": title,
        "workflow_url": sr.get_app_url(),
        "input_prompt": build_input_prompt_preview(input_prompt),
    }
    if input_audio := request_body.get("input_audio"):
        bulk_progress["input_audio"] = input_audio
    if credits_used is not None:
        bulk_progress["credits_used"] = credits_used
    elif previous_progress and "credits_used" in previous_progress:
        bulk_progress["credits_used"] = previous_progress["credits_used"]
    if workflow_run_time_seconds is not None:
        bulk_progress["workflow_run_time_seconds"] = workflow_run_time_seconds
    if workflow_credits is not None:
        bulk_progress["workflow_credits"] = workflow_credits
    if error_msg:
        bulk_progress["error_msg"] = error_msg

    if current_workflow_completed:
        bulk_progress["last_completed_workflow_title"] = title
        bulk_progress["last_completed_workflow_url"] = sr.get_app_url()
        if workflow_run_time_seconds is not None:
            bulk_progress["last_completed_run_time_seconds"] = workflow_run_time_seconds
        if workflow_credits is not None:
            bulk_progress["last_completed_credits"] = workflow_credits
    elif previous_progress:
        for key in (
            "last_completed_workflow_title",
            "last_completed_workflow_url",
            "last_completed_run_time_seconds",
            "last_completed_credits",
        ):
            if key in previous_progress:
                bulk_progress[key] = previous_progress[key]

    return bulk_progress


def build_input_prompt_preview(input_prompt: str | None) -> str:
    if not input_prompt:
        return ""

    if len(input_prompt) <= BULK_INPUT_PROMPT_PREVIEW_CHARS:
        return input_prompt

    return input_prompt[: BULK_INPUT_PROMPT_PREVIEW_CHARS - 3].rstrip() + "..."


def bulk_progress_percent(progress: BulkProgressCounts | None) -> int:
    if not progress or not progress["total_unit_runs"]:
        return 0
    return round(progress["completed_unit_runs"] / progress["total_unit_runs"] * 100)
