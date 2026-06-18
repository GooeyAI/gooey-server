from __future__ import annotations

import datetime

import gooey_gui as gui

from daras_ai_v2.base import BasePage, RecipeRunState, StateKeys
from gooey_gui.types.bulk_progress_props import (
    BulkEvalProgress,
    BulkProgress,
    BulkProgressCardProps,
    BulkProgressSnapshot,
    BulkRunnerRunState,
)
from widgets.bulk_progress_state import is_bulk_progress_complete


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
        progress=coerce_bulk_progress(progress),
        is_cancelled=is_cancelled,
        recipe_run_state=BasePage.get_run_state(session),
        elapsed_seconds=elapsed_seconds,
        eval_progress=coerce_bulk_eval_progress(session.get("eval_progress")),
    )
    if not snapshot:
        return

    props = BulkProgressCardProps(
        snapshot=snapshot,
        rerun_all_key="-submit-workflow",
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

    return BulkProgressSnapshot.from_bulk_progress(
        progress=progress,
        run_state=run_state,
        elapsed_seconds=elapsed_seconds,
        eval_progress=eval_progress,
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
        if progress.phase == "evaluating":
            return BulkRunnerRunState.evaluating
        return BulkRunnerRunState.running

    if is_bulk_progress_complete(progress):
        return BulkRunnerRunState.complete

    return BulkRunnerRunState.stopped


def coerce_bulk_progress(progress: BulkProgress | dict) -> BulkProgress:
    if isinstance(progress, BulkProgress):
        return progress
    return BulkProgress.model_validate(progress)


def coerce_bulk_eval_progress(
    eval_progress: BulkEvalProgress | dict | None,
) -> BulkEvalProgress | None:
    if not eval_progress:
        return None
    if isinstance(eval_progress, BulkEvalProgress):
        return eval_progress
    return BulkEvalProgress.model_validate(eval_progress)
