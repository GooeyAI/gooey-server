import {
  formatAverageCredits,
  formatAverageRunTime,
  formatCredits,
  formatElapsed,
} from "./bulkProgressFormat";
import type {
  ActiveCardModel,
  BulkProgressSnapshot,
  BulkRunnerRunState,
  CardModel,
  CompleteCardModel,
  DetailDisplay,
  WorkflowDisplay,
} from "./bulkProgress.types";

type ActiveRunState = Exclude<BulkRunnerRunState, "complete">;

type ActiveRunStateProfile = {
  title: string;
  tickElapsed: boolean;
  showRerun: boolean;
  marker: ActiveCardModel["marker"];
  cardClass: string;
};

const ACTIVE_RUN_STATE_PROFILE: Record<ActiveRunState, ActiveRunStateProfile> = {
  running: {
    title: "Running...",
    tickElapsed: true,
    showRerun: false,
    marker: "dot",
    cardClass: "running",
  },
  stopping: {
    title: "Stopping...",
    tickElapsed: true,
    showRerun: false,
    marker: "dot",
    cardClass: "running",
  },
  evaluating: {
    title: "Running evals...",
    tickElapsed: true,
    showRerun: false,
    marker: "dot",
    cardClass: "running",
  },
  error: {
    title: "Bulk run failed",
    tickElapsed: false,
    showRerun: true,
    marker: "dot",
    cardClass: "error",
  },
  stopped: {
    title: "Bulk run stopped",
    tickElapsed: false,
    showRerun: true,
    marker: "stop",
    cardClass: "stopped",
  },
};

export function buildCardModel(
  snapshot: BulkProgressSnapshot,
  liveElapsedSeconds: number | null | undefined
): CardModel {
  switch (snapshot.run_state) {
    case "complete":
      return buildCompleteModel(snapshot);
    case "evaluating":
      return buildEvaluatingModel(snapshot, liveElapsedSeconds);
    case "running":
      return buildInProgressUnitRunModel(snapshot, {
        runState: "running",
        liveElapsedSeconds,
      });
    case "stopping":
      return buildInProgressUnitRunModel(snapshot, {
        runState: "stopping",
        liveElapsedSeconds,
      });
    case "stopped":
      return buildTerminalUnitRunModel(snapshot, "stopped");
    case "error":
      return buildTerminalUnitRunModel(snapshot, "error");
  }
}

export function snapshotTicksElapsed(snapshot: BulkProgressSnapshot): boolean {
  return (
    snapshot.run_state !== "complete" &&
    ACTIVE_RUN_STATE_PROFILE[snapshot.run_state].tickElapsed
  );
}

function buildCompleteModel(snapshot: BulkProgressSnapshot): CompleteCardModel {
  return {
    kind: "complete",
    title: "Bulk run complete",
    totalRuns: snapshot.total_unit_runs,
    totalRows: snapshot.total_rows,
    rowsCaption: `× ${snapshot.total_workflows} workflows`,
    totalTime:
      snapshot.elapsed_seconds != null
        ? formatElapsed(snapshot.elapsed_seconds)
        : "-",
    averageRunTime: formatAverageRunTime(snapshot),
    credits:
      snapshot.credits_used != null ? String(snapshot.credits_used) : "-",
    averageCredits: formatAverageCredits(snapshot),
    showRerun: true,
  };
}

function buildEvaluatingModel(
  snapshot: BulkProgressSnapshot,
  liveElapsedSeconds: number | null | undefined
): ActiveCardModel {
  const profile = ACTIVE_RUN_STATE_PROFILE.evaluating;
  const evalCounts =
    snapshot.eval_current != null && snapshot.eval_total != null
      ? { current: snapshot.eval_current, total: snapshot.eval_total }
      : null;
  const ring = getEvalRingDisplay(evalCounts);
  const metaParts: string[] = [];

  if (evalCounts) {
    metaParts.push(`${evalCounts.current} of ${evalCounts.total}`);
  }
  appendCreditsAndElapsed(metaParts, snapshot, liveElapsedSeconds);

  return activeFromProfile(profile, {
    headline: snapshot.eval_workflow_title || "Eval workflow",
    metaParts,
    ringPercent: ring.ringPercent,
    ringLabel: ring.ringLabel,
    detail: null,
  });
}

function buildInProgressUnitRunModel(
  snapshot: BulkProgressSnapshot,
  variant: {
    runState: "running" | "stopping";
    liveElapsedSeconds: number | null | undefined;
  }
): ActiveCardModel {
  const profile = ACTIVE_RUN_STATE_PROFILE[variant.runState];
  const ring = unitRunRingFields(snapshot);
  const metaParts = [
    `${snapshot.completed_unit_runs} of ${snapshot.total_unit_runs} total runs`,
  ];
  appendCreditsAndElapsed(metaParts, snapshot, variant.liveElapsedSeconds);

  return activeFromProfile(profile, {
    ...ring,
    metaParts,
    detail: buildDetail(snapshot, {
      rowLabel: `Processing row ${snapshot.current_row_number} of ${snapshot.total_rows}`,
      showStoppingMessage: variant.runState === "stopping",
      failedAt: null,
      workflowElapsedSeconds: 0,
    }),
  });
}

function buildTerminalUnitRunModel(
  snapshot: BulkProgressSnapshot,
  runState: "stopped" | "error"
): ActiveCardModel {
  const profile = ACTIVE_RUN_STATE_PROFILE[runState];
  const ring = unitRunRingFields(snapshot);
  const remaining = Math.max(
    snapshot.total_unit_runs - snapshot.completed_unit_runs,
    0
  );
  const metaParts = [
    `${snapshot.completed_unit_runs} of ${snapshot.total_unit_runs} total runs (${remaining} remaining)`,
  ];
  const elapsed = runState === "stopped" ? snapshot.elapsed_seconds : undefined;
  appendCreditsAndElapsed(metaParts, snapshot, elapsed);
  const rowLabel =
    runState === "error"
      ? `Failed on row ${snapshot.current_row_number} of ${snapshot.total_rows}`
      : `Started row ${snapshot.current_row_number} of ${snapshot.total_rows}`;

  return activeFromProfile(profile, {
    ...ring,
    metaParts,
    detail: buildDetail(snapshot, {
      rowLabel,
      showStoppingMessage: false,
      failedAt:
        runState === "error"
          ? snapshot.workflow_run_time_seconds ?? null
          : null,
    }),
  });
}

function activeFromProfile(
  profile: ActiveRunStateProfile,
  fields: {
    headline: string;
    metaParts: string[];
    ringPercent: number;
    ringLabel: string;
    detail: DetailDisplay | null;
  }
): ActiveCardModel {
  return {
    kind: "active",
    cardClass: profile.cardClass,
    title: profile.title,
    headline: fields.headline,
    metaParts: fields.metaParts,
    marker: profile.marker,
    ringPercent: fields.ringPercent,
    ringLabel: fields.ringLabel,
    detail: fields.detail,
    showRerun: profile.showRerun,
  };
}

function appendCreditsAndElapsed(
  metaParts: string[],
  snapshot: BulkProgressSnapshot,
  elapsedSeconds: number | null | undefined
) {
  if (snapshot.credits_used != null) {
    metaParts.push(formatCredits(snapshot.credits_used));
  }
  if (elapsedSeconds != null) {
    metaParts.push(formatElapsed(elapsedSeconds));
  }
}

function buildDetail(
  snapshot: BulkProgressSnapshot,
  {
    rowLabel,
    showStoppingMessage,
    failedAt,
    workflowElapsedSeconds = null,
  }: {
    rowLabel: string;
    showStoppingMessage: boolean;
    failedAt: number | null;
    workflowElapsedSeconds?: number | null;
  }
): DetailDisplay {
  const currentTitle = snapshot.workflow_title.trim();
  const lastTitle = snapshot.last_completed_workflow_title?.trim();
  const lastUrl = snapshot.last_completed_workflow_url;
  let workflow: WorkflowDisplay | null = null;

  if (currentTitle && snapshot.workflow_url) {
    const workflowNumber = Math.max(snapshot.current_workflow_number, 1);
    const prefix = `workflow ${workflowNumber} of ${snapshot.total_workflows}`;
    workflow = {
      prefix,
      title: currentTitle,
      url: snapshot.workflow_url,
      failedAt,
      elapsedSeconds: workflowElapsedSeconds,
    };
  }

  return {
    rowLabel,
    showStoppingMessage,
    workflow,
    inputPrompt: snapshot.input_prompt,
    inputAudioUrl: snapshot.input_audio,
    lastCompleted:
      lastTitle && lastUrl
        ? {
            title: lastTitle,
            url: lastUrl,
            credits: snapshot.last_completed_credits,
            runTimeSeconds: snapshot.last_completed_run_time_seconds,
          }
        : undefined,
  };
}

function getEvalRingDisplay(
  evalCounts: { current: number; total: number } | null
): { ringPercent: number; ringLabel: string } {
  if (!evalCounts) {
    return { ringPercent: 0, ringLabel: "…" };
  }
  if (!evalCounts.total) {
    return {
      ringPercent: 0,
      ringLabel: `${evalCounts.current}/${evalCounts.total}`,
    };
  }
  const completedEvals = Math.max(evalCounts.current - 1, 0);
  const ringPercent = Math.min(
    Math.max(Math.round((completedEvals / evalCounts.total) * 100), 0),
    100
  );
  return {
    ringPercent,
    ringLabel: `${completedEvals}/${evalCounts.total}`,
  };
}

function unitRunRingFields(snapshot: BulkProgressSnapshot) {
  let ringPercent = 0;
  if (snapshot.total_unit_runs) {
    ringPercent = Math.min(
      Math.max(
        Math.round((snapshot.completed_unit_runs / snapshot.total_unit_runs) * 100),
        0
      ),
      100
    );
  }
  return {
    ringPercent,
    ringLabel: `${ringPercent}%`,
    headline: `${ringPercent}% completed`,
  };
}
