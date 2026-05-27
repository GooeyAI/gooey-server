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
  ringAccent: string;
};

const ACTIVE_RUN_STATE_PROFILE: Record<ActiveRunState, ActiveRunStateProfile> = {
  running: {
    title: "Running...",
    tickElapsed: true,
    showRerun: false,
    marker: "dot",
    cardClass: "running",
    ringAccent: "#070b1a",
  },
  stopping: {
    title: "Stopping...",
    tickElapsed: true,
    showRerun: false,
    marker: "dot",
    cardClass: "running",
    ringAccent: "#070b1a",
  },
  evaluating: {
    title: "Running evals...",
    tickElapsed: true,
    showRerun: false,
    marker: "dot",
    cardClass: "running",
    ringAccent: "#070b1a",
  },
  error: {
    title: "Bulk run failed",
    tickElapsed: false,
    showRerun: true,
    marker: "dot",
    cardClass: "error",
    ringAccent: "#b42318",
  },
  stopped: {
    title: "Bulk run stopped",
    tickElapsed: false,
    showRerun: true,
    marker: "stop",
    cardClass: "stopped",
    ringAccent: "#9d7b1f",
  },
};

export function buildCardModel(
  snapshot: BulkProgressSnapshot,
  liveElapsedSeconds: number | null | undefined
): CardModel {
  switch (snapshot.runState) {
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
    snapshot.runState !== "complete" &&
    ACTIVE_RUN_STATE_PROFILE[snapshot.runState].tickElapsed
  );
}

function buildCompleteModel(snapshot: BulkProgressSnapshot): CompleteCardModel {
  return {
    kind: "complete",
    title: "Bulk run complete",
    totalRuns: snapshot.totalUnitRuns,
    totalRows: snapshot.totalRows,
    rowsCaption: `× ${snapshot.totalWorkflows} workflows`,
    totalTime:
      snapshot.elapsedSeconds != null
        ? formatElapsed(snapshot.elapsedSeconds)
        : "-",
    averageRunTime: formatAverageRunTime(snapshot),
    credits:
      snapshot.creditsUsed != null ? String(snapshot.creditsUsed) : "-",
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
    snapshot.evalCurrent != null && snapshot.evalTotal != null
      ? { current: snapshot.evalCurrent, total: snapshot.evalTotal }
      : null;
  const ring = getEvalRingDisplay(evalCounts);
  const metaParts: string[] = [];

  if (evalCounts) {
    metaParts.push(`${evalCounts.current} of ${evalCounts.total}`);
  }
  appendCreditsAndElapsed(metaParts, snapshot, liveElapsedSeconds);

  return activeFromProfile(profile, {
    headline: snapshot.evalWorkflowTitle || "Eval workflow",
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
    `${snapshot.completedUnitRuns} of ${snapshot.totalUnitRuns} total runs`,
  ];
  appendCreditsAndElapsed(metaParts, snapshot, variant.liveElapsedSeconds);

  return activeFromProfile(profile, {
    ...ring,
    metaParts,
    detail: buildDetail(snapshot, {
      rowLabel: `Processing row ${snapshot.currentRowNumber} of ${snapshot.totalRows}`,
      showStoppingMessage: variant.runState === "stopping",
      capitalized: false,
      failedAt: null,
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
    snapshot.totalUnitRuns - snapshot.completedUnitRuns,
    0
  );
  const metaParts = [
    `${snapshot.completedUnitRuns} of ${snapshot.totalUnitRuns} Total runs (${remaining} remaining)`,
  ];
  const elapsed = runState === "stopped" ? snapshot.elapsedSeconds : undefined;
  appendCreditsAndElapsed(metaParts, snapshot, elapsed);
  const rowLabel =
    runState === "error"
      ? `Failed on row ${snapshot.currentRowNumber} of ${snapshot.totalRows}`
      : `Started row ${snapshot.currentRowNumber} of ${snapshot.totalRows}`;

  return activeFromProfile(profile, {
    ...ring,
    metaParts,
    detail: buildDetail(snapshot, {
      rowLabel,
      showStoppingMessage: false,
      capitalized: true,
      failedAt:
        runState === "error"
          ? snapshot.currentWorkflowRunTimeSeconds ?? null
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
    ringAccent: profile.ringAccent,
    detail: fields.detail,
    showRerun: profile.showRerun,
  };
}

function appendCreditsAndElapsed(
  metaParts: string[],
  snapshot: BulkProgressSnapshot,
  elapsedSeconds: number | null | undefined
) {
  if (snapshot.creditsUsed != null) {
    metaParts.push(formatCredits(snapshot.creditsUsed));
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
    capitalized,
    failedAt,
  }: {
    rowLabel: string;
    showStoppingMessage: boolean;
    capitalized: boolean;
    failedAt: number | null;
  }
): DetailDisplay {
  const lastTitle = snapshot.lastCompletedWorkflowTitle;
  const lastUrl = snapshot.lastCompletedWorkflowUrl;

  return {
    rowLabel,
    showStoppingMessage,
    workflow: buildWorkflowDisplay(snapshot, { capitalized, failedAt }),
    inputPrompt: snapshot.inputPrompt,
    inputAudioUrl: snapshot.inputAudioUrl,
    lastCompleted:
      lastTitle && lastUrl
        ? {
            title: lastTitle,
            url: lastUrl,
            credits: snapshot.lastCompletedCredits,
            runTimeSeconds: snapshot.lastCompletedRunTimeSeconds,
          }
        : undefined,
  };
}

function buildWorkflowDisplay(
  snapshot: BulkProgressSnapshot,
  options: { capitalized: boolean; failedAt: number | null }
): WorkflowDisplay | null {
  if (!snapshot.currentWorkflowTitle || !snapshot.currentWorkflowUrl) {
    return null;
  }

  const workflowNumber = Math.max(snapshot.currentWorkflowNumber, 1);
  const prefix = options.capitalized
    ? `Workflow ${workflowNumber} of ${snapshot.totalWorkflows}:`
    : `workflow ${workflowNumber} of ${snapshot.totalWorkflows}`;

  return {
    prefix,
    title: snapshot.currentWorkflowTitle,
    url: snapshot.currentWorkflowUrl,
    failedAt: options.failedAt,
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
  const ringPercent = Math.round((evalCounts.current / evalCounts.total) * 100);
  return {
    ringPercent,
    ringLabel: `${evalCounts.current}/${evalCounts.total}`,
  };
}

function unitRunRingFields(snapshot: BulkProgressSnapshot) {
  const ringPercent = unitRunPercent(snapshot);
  return {
    ringPercent,
    ringLabel: `${ringPercent}%`,
    headline: `${ringPercent}% Completed`,
  };
}

function unitRunPercent(snapshot: BulkProgressSnapshot) {
  if (!snapshot.totalUnitRuns) {
    return 0;
  }
  return Math.round(
    (snapshot.completedUnitRuns / snapshot.totalUnitRuns) * 100
  );
}
