import { useEffect, useState } from "react";

import "./BulkProgressCard.css";

type BulkProgressState = "running" | "stopped" | "complete" | "error";

type BulkProgress = {
  completed_unit_runs: number;
  total_unit_runs: number;
  completed_row_groups: number;
  total_row_groups: number;
  completed_rows: number;
  total_rows: number;
  current_row_number: number;
  current_workflow_number: number;
  total_workflows: number;
  workflow_title: string;
  workflow_url: string;
  input_prompt: string;
  input_audio?: string;
  credits_used?: number;
  workflow_run_time_seconds?: number;
  workflow_credits?: number;
  last_completed_workflow_title?: string;
  last_completed_workflow_url?: string;
  last_completed_run_time_seconds?: number;
  last_completed_credits?: number;
  error_msg?: string;
};

type BulkProgressCardProps = {
  progress: BulkProgress;
  progressState: BulkProgressState;
  stopRequested?: boolean;
  elapsedSeconds?: number | null;
  rerunAllKey?: string | null;
};

function useLiveElapsedSeconds(
  elapsedSeconds: number | null | undefined,
  isTicking: boolean
) {
  const [liveElapsedSeconds, setLiveElapsedSeconds] = useState(elapsedSeconds);

  useEffect(() => {
    setLiveElapsedSeconds(elapsedSeconds);
  }, [elapsedSeconds]);

  useEffect(() => {
    if (!isTicking || elapsedSeconds == null) {
      return;
    }

    const startedAt = Date.now() - elapsedSeconds * 1000;
    const intervalId = window.setInterval(() => {
      setLiveElapsedSeconds((Date.now() - startedAt) / 1000);
    }, 1000);

    return () => window.clearInterval(intervalId);
  }, [elapsedSeconds, isTicking]);

  return liveElapsedSeconds;
}

export function BulkProgressCard({
  progress,
  progressState,
  stopRequested,
  elapsedSeconds,
  rerunAllKey,
}: BulkProgressCardProps) {
  const liveElapsedSeconds = useLiveElapsedSeconds(
    elapsedSeconds,
    progressState === "running" || Boolean(stopRequested)
  );
  const view = buildView(
    progress,
    progressState,
    liveElapsedSeconds,
    stopRequested
  );

  if (progressState === "complete") {
    return (
      <div className="bulk-progress-card bulk-progress-card-complete">
        <div className="bulk-progress-complete-header">
          <span className="bulk-progress-status-icon">
            <i className="fa-solid fa-check" />
          </span>
          <div>
            <div className="bulk-progress-kicker">
              <strong>{view.title}</strong>
            </div>
          </div>
        </div>
        <div className="bulk-progress-summary-grid">
          <SummaryStat label="Total runs" value={progress.total_unit_runs}>
            all completed
          </SummaryStat>
          <SummaryStat label="Total time" value={view.elapsed || "-"}>
            {view.averageRunTime}
          </SummaryStat>
          <SummaryStat label="Credits" value={progress.credits_used || "-"}>
            {view.averageCredits}
          </SummaryStat>
          <SummaryStat label="Rows" value={progress.total_rows}>
            &times; {progress.total_workflows} workflows
          </SummaryStat>
        </div>
        <ProgressActions
          progress={progress}
          state={progressState}
          rerunAllKey={rerunAllKey}
        />
      </div>
    );
  }

  return (
    <div className={`bulk-progress-card bulk-progress-card-${progressState}`}>
      <div className="bulk-progress-running-header">
        <div className="bulk-progress-main">
          <div className="bulk-progress-main-left">
            <ProgressRing percent={view.percent} state={progressState} />
          </div>
          <div className="bulk-progress-main-right">
            <div className="bulk-progress-copy">
              <div className="bulk-progress-heading-row">
                <div className="bulk-progress-kicker">
                  <span className="bulk-progress-dot" />
                  <strong>{view.title}</strong>
                </div>
              </div>
              <div className="bulk-progress-headline">{view.headline}</div>
              <MetaRow parts={view.metaParts} />
            </div>
          </div>
        </div>
      </div>
      <ProgressDetail
        progress={progress}
        state={progressState}
        stopRequested={stopRequested}
      />
      <ProgressActions
        progress={progress}
        state={progressState}
        rerunAllKey={rerunAllKey}
      />
    </div>
  );
}

function SummaryStat({
  label,
  value,
  children,
}: {
  label: string;
  value: number | string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="bulk-progress-stat-label">{label}</div>
      <div className="bulk-progress-stat-value">{value}</div>
      <div className="bulk-progress-stat-caption">{children}</div>
    </div>
  );
}

function ProgressRing({
  percent,
  state,
}: {
  percent: number;
  state: BulkProgressState;
}) {
  const circumference = 251.33;
  const boundedPercent = Math.max(Math.min(percent, 100), 0);
  const remaining = circumference - (circumference * boundedPercent) / 100;

  return (
    <div
      className="bulk-progress-ring"
      style={
        {
          "--bulk-progress-accent": stateColor(state),
        } as React.CSSProperties
      }
    >
      <svg viewBox="0 0 100 100" aria-hidden="true">
        <circle className="bulk-progress-ring-track" cx="50" cy="50" r="40" />
        <circle
          className="bulk-progress-ring-bar"
          cx="50"
          cy="50"
          r="40"
          strokeDasharray={circumference.toFixed(2)}
          strokeDashoffset={remaining.toFixed(2)}
        />
      </svg>
      <div>
        <strong>{percent}%</strong>
      </div>
    </div>
  );
}

function MetaRow({ parts }: { parts: Array<React.ReactNode> }) {
  const nodes: React.ReactNode[] = [];
  parts.forEach((part, index) => {
    if (index) {
      nodes.push(
        <span
          aria-hidden="true"
          className="bulk-progress-meta-separator"
          key={`separator-${index}`}
        >
          &middot;
        </span>
      );
    }
    nodes.push(
      <span className="bulk-progress-meta-item" key={`part-${index}`}>
        {part}
      </span>
    );
  });

  return <div className="bulk-progress-meta">{nodes}</div>;
}

function ProgressDetail({
  progress,
  state,
  stopRequested,
}: {
  progress: BulkProgress;
  state: BulkProgressState;
  stopRequested?: boolean;
}) {
  if (state === "complete") {
    return null;
  }

  return (
    <div className="bulk-progress-detail">
      <div className="bulk-progress-current">
        <strong>
          {currentActionLabel(state)} row {progress.current_row_number} of{" "}
          {progress.total_rows}
        </strong>
      </div>
      {stopRequested ? (
        <div className="bulk-progress-stop-pending">
          We're trying our best to cancel this run, please be patient.
        </div>
      ) : null}
      {state === "running" ? <WorkflowLink progress={progress} /> : null}
      {state === "stopped" || state === "error" ? (
        <StoppedWorkflow progress={progress} />
      ) : null}
      {progress.input_prompt ? (
        <PromptPreview inputPrompt={progress.input_prompt} />
      ) : null}
      {progress.input_audio ? (
        <InputAudioLink inputAudio={progress.input_audio} />
      ) : null}
      {state === "error" && progress.error_msg ? (
        <div className="bulk-progress-error-message">{progress.error_msg}</div>
      ) : null}
      {state === "running" || state === "stopped" || state === "error" ? (
        <LastCompleted progress={progress} />
      ) : null}
    </div>
  );
}

function PromptPreview({ inputPrompt }: { inputPrompt: string }) {
  return (
    <div className="bulk-progress-input">
      <div className="bulk-progress-input-text">
        <span>input_prompt:</span> {inputPrompt}
      </div>
    </div>
  );
}

function WorkflowLink({ progress }: { progress: BulkProgress }) {
  if (!progress.workflow_title || !progress.workflow_url) {
    return null;
  }

  return (
    <div className="bulk-progress-workflow">
      <span className="bulk-progress-workflow-main">
        <span className="bulk-progress-workflow-prefix">
          workflow {progress.current_workflow_number} of{" "}
          {progress.total_workflows}{" "}
        </span>
        <a
          className="bulk-progress-workflow-title"
          href={progress.workflow_url}
          target="_blank"
          rel="noopener noreferrer"
        >
          <strong>{progress.workflow_title}</strong>
        </a>
      </span>
    </div>
  );
}

function StoppedWorkflow({ progress }: { progress: BulkProgress }) {
  if (!progress.workflow_title || !progress.workflow_url) {
    return null;
  }

  return (
    <div className="bulk-progress-workflow">
      <span className="bulk-progress-workflow-main">
        <span className="bulk-progress-workflow-prefix">
          Workflow {progress.current_workflow_number} of{" "}
          {progress.total_workflows}:{" "}
        </span>
        <a
          className="bulk-progress-workflow-title"
          href={progress.workflow_url}
          target="_blank"
          rel="noopener noreferrer"
        >
          <strong>{progress.workflow_title}</strong>
        </a>
      </span>
    </div>
  );
}

function InputAudioLink({ inputAudio }: { inputAudio: string }) {
  return (
    <div className="bulk-progress-input">
      <span>input_audio:</span>{" "}
      <a href={inputAudio} target="_blank" rel="noopener noreferrer">
        View audio &rarr;
      </a>
    </div>
  );
}

function LastCompleted({ progress }: { progress: BulkProgress }) {
  const title = progress.last_completed_workflow_title;
  const url = progress.last_completed_workflow_url;
  if (!title || !url) {
    return null;
  }
  const runTime = formatRunDuration(progress.last_completed_run_time_seconds);

  return (
    <div className="bulk-progress-last-completed">
      <span className="bulk-progress-last-completed-label">Last completed</span>
      <a
        className="bulk-progress-last-completed-title"
        href={url}
        target="_blank"
        rel="noopener noreferrer"
      >
        {title}
      </a>
      {runTime || progress.last_completed_credits ? (
        <span className="bulk-progress-last-completed-meta">
          {runTime ? <> &middot; {runTime}</> : null}
          {progress.last_completed_credits ? (
            <> &middot; {progress.last_completed_credits} Cr</>
          ) : null}
        </span>
      ) : null}
    </div>
  );
}

function ProgressActions({
  progress,
  state,
  rerunAllKey,
}: {
  progress: BulkProgress;
  state: BulkProgressState;
  rerunAllKey?: string | null;
}) {
  if (!rerunAllKey) {
    return null;
  }

  return (
    <div className="bulk-progress-actions">
      {state === "complete" && rerunAllKey ? (
        <SubmitAction
          name={rerunAllKey}
          label="Re-run all"
          icon="fa-solid fa-rotate-right"
        />
      ) : null}
    </div>
  );
}

function SubmitAction({
  name,
  label,
  icon,
  variant = "primary",
}: {
  name: string;
  label: string;
  icon: string;
  variant?: "primary" | "secondary" | "tertiary";
}) {
  return (
    <button
      className={`btn btn-theme btn-${variant} bulk-progress-action`}
      name={name}
      type="submit"
      value="1"
    >
      <i aria-hidden="true" className={icon} />
      {label}
    </button>
  );
}

function buildView(
  progress: BulkProgress,
  state: BulkProgressState,
  elapsedSeconds?: number | null,
  stopRequested?: boolean
) {
  const percent = bulkProgressPercent(progress);
  const remainingUnitRuns = Math.max(
    progress.total_unit_runs - progress.completed_unit_runs,
    0
  );
  const metaParts: Array<React.ReactNode> = [];
  let title = "Running...";
  let headline = `${progress.completed_rows} of ${progress.total_rows} rows`;

  if (state === "stopped") {
    title = stopRequested ? "Stopping..." : "Bulk was stopped";
    headline = `${percent}% Completed`;
    metaParts.push(
      `${progress.completed_unit_runs} of ${progress.total_unit_runs} Total runs (${remainingUnitRuns} remaining)`
    );
  } else if (state === "error") {
    title = "Bulk run failed";
    headline = `${percent}% Completed`;
    metaParts.push(
      `${progress.completed_unit_runs} of ${progress.total_unit_runs} Total runs (${remainingUnitRuns} remaining)`
    );
  } else if (state === "complete") {
    title = "Bulk run complete";
    headline = `${progress.total_rows} rows complete`;
  } else {
    title = stopRequested ? "Stopping..." : "Running...";
    headline = `${percent}% Completed`;
    metaParts.push(
      `${progress.completed_unit_runs} of ${progress.total_unit_runs} total runs`
    );
  }

  const elapsed = formatRunDuration(elapsedSeconds);
  if (elapsed) {
    metaParts.push(elapsed);
  }

  if (progress.credits_used) {
    metaParts.push(`${progress.credits_used} Cr`);
  }

  return {
    averageRunTime: formatAverageRunTime(
      progress.total_unit_runs,
      elapsedSeconds
    ),
    averageCredits: formatAverageCredits(
      progress.total_unit_runs,
      progress.credits_used
    ),
    elapsed,
    headline,
    metaParts,
    percent,
    title,
  };
}

function bulkProgressPercent(progress: BulkProgress) {
  if (!progress.total_unit_runs) {
    return 0;
  }
  return Math.round(
    (progress.completed_unit_runs / progress.total_unit_runs) * 100
  );
}

function currentActionLabel(state: BulkProgressState) {
  if (state === "error") {
    return "Failed on";
  }
  if (state === "stopped") {
    return "Started";
  }
  return "Processing";
}

function stateColor(state: BulkProgressState) {
  if (state === "stopped") {
    return "#9d7b1f";
  }
  if (state === "error") {
    return "#b42318";
  }
  if (state === "complete") {
    return "#3f9438";
  }
  return "#070b1a";
}

function formatAverageRunTime(
  totalUnitRuns: number,
  elapsedSeconds?: number | null
) {
  if (!elapsedSeconds || totalUnitRuns <= 0) {
    return "-";
  }
  return `${(elapsedSeconds / totalUnitRuns).toFixed(1)}s avg / run`;
}

function formatAverageCredits(
  totalUnitRuns: number,
  creditsUsed?: number | null
) {
  if (!creditsUsed || totalUnitRuns <= 0) {
    return "-";
  }
  return `${(creditsUsed / totalUnitRuns).toFixed(1)} Cr / run`;
}

function formatRunDuration(seconds?: number | null) {
  if (seconds == null) {
    return null;
  }
  if (seconds < 60) {
    return `${Math.round(seconds)}s`;
  }
  return formatDuration(seconds);
}

function formatDuration(seconds?: number | null) {
  if (seconds == null) {
    return null;
  }

  let roundedSeconds = Math.max(Math.round(seconds), 0);
  const minutes = Math.floor(roundedSeconds / 60);
  roundedSeconds %= 60;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  if (hours) {
    return `${hours}h ${remainingMinutes}m`;
  }
  if (minutes) {
    return `${minutes}m ${roundedSeconds}s`;
  }
  return `${roundedSeconds}s`;
}
