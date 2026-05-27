import { useEffect, useState } from "react";

import { buildCardModel, snapshotTicksElapsed } from "./bulkProgressCardModel";
import { formatCredits, formatElapsed } from "./bulkProgressFormat";
import type {
  BulkProgressCardProps,
  DetailDisplay,
  WorkflowDisplay,
} from "./bulkProgress.types";

import "./BulkProgressCard.css";

export function BulkProgressCard({
  snapshot,
  rerunAllKey,
}: BulkProgressCardProps) {
  const liveElapsedSeconds = useLiveElapsedSeconds(
    snapshot.elapsedSeconds,
    snapshotTicksElapsed(snapshot)
  );
  const model = buildCardModel(snapshot, liveElapsedSeconds);

  if (model.kind === "complete") {
    return (
      <div className="bulk-progress-card bulk-progress-card-complete">
        <div className="bulk-progress-complete-header">
          <span className="bulk-progress-status-icon">
            <i className="fa-solid fa-check" />
          </span>
          <div>
            <div className="bulk-progress-kicker">
              <strong>{model.title}</strong>
            </div>
          </div>
        </div>
        <div className="bulk-progress-summary-grid">
          <SummaryStat label="Total runs" value={model.totalRuns}>
            all completed
          </SummaryStat>
          <SummaryStat label="Total time" value={model.totalTime}>
            {model.averageRunTime}
          </SummaryStat>
          <SummaryStat label="Credits" value={model.credits}>
            {model.averageCredits}
          </SummaryStat>
          <SummaryStat label="Rows" value={model.totalRows}>
            {model.rowsCaption}
          </SummaryStat>
        </div>
        <RerunAllActions rerunAllKey={rerunAllKey} showRerun={model.showRerun} />
      </div>
    );
  }

  return (
    <div className={`bulk-progress-card bulk-progress-card-${model.cardClass}`}>
      <div className="bulk-progress-running-header">
        <div className="bulk-progress-main">
          <div className="bulk-progress-main-left">
            <ProgressRing
              ringPercent={model.ringPercent}
              ringLabel={model.ringLabel}
              ringAccent={model.ringAccent}
            />
          </div>
          <div className="bulk-progress-main-right">
            <div className="bulk-progress-copy">
              <div className="bulk-progress-kicker">
                {model.marker === "stop" && (
                  <i
                    aria-hidden="true"
                    className="fa-solid fa-circle-stop bulk-progress-stop-icon"
                  />
                )}
                {model.marker === "dot" && <span className="bulk-progress-dot" />}
                <strong>{model.title}</strong>
              </div>
              <div className="bulk-progress-headline">{model.headline}</div>
              <MetaRow parts={model.metaParts} />
            </div>
          </div>
        </div>
      </div>
      {model.detail ? <ProgressDetail detail={model.detail} /> : null}
      <RerunAllActions rerunAllKey={rerunAllKey} showRerun={model.showRerun} />
    </div>
  );
}

function RerunAllActions({
  rerunAllKey,
  showRerun,
}: {
  rerunAllKey?: string | null;
  showRerun: boolean;
}) {
  if (!rerunAllKey || !showRerun) {
    return null;
  }

  return (
    <div className="bulk-progress-actions">
      <button
        className="btn btn-theme btn-tertiary bulk-progress-action"
        name={rerunAllKey}
        type="submit"
        value="1"
      >
        <i aria-hidden="true" className="fa-solid fa-rotate-right" />
        Re-run all
      </button>
    </div>
  );
}

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
  ringPercent,
  ringLabel,
  ringAccent,
}: {
  ringPercent: number;
  ringLabel: string;
  ringAccent: string;
}) {
  const circumference = 251.33;
  const boundedRingPercent = Math.max(Math.min(ringPercent, 100), 0);
  const remaining = circumference - (circumference * boundedRingPercent) / 100;

  return (
    <div
      className="bulk-progress-ring"
      style={{ ["--bulk-progress-accent"]: ringAccent } as React.CSSProperties}
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
        <strong>{ringLabel}</strong>
      </div>
    </div>
  );
}

function MetaRow({ parts }: { parts: string[] }) {
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

function ProgressDetail({ detail }: { detail: DetailDisplay }) {
  return (
    <div className="bulk-progress-detail">
      <div className="bulk-progress-current">
        <strong>{detail.rowLabel}</strong>
      </div>
      {detail.showStoppingMessage ? (
        <div className="bulk-progress-stop-pending">
          We're trying our best to cancel this run, please be patient.
        </div>
      ) : null}
      {detail.workflow ? (
        <WorkflowRow workflow={detail.workflow} />
      ) : null}
      {detail.inputPrompt ? (
        <div className="bulk-progress-input">
          <div className="bulk-progress-input-text">
            <span>input_prompt:</span> {detail.inputPrompt}
          </div>
        </div>
      ) : null}
      {detail.inputAudioUrl ? (
        <div className="bulk-progress-input">
          <span>input_audio:</span>{" "}
          <a
            href={detail.inputAudioUrl}
            target="_blank"
            rel="noopener noreferrer"
          >
            View audio &rarr;
          </a>
        </div>
      ) : null}
      {detail.lastCompleted ? (
        <LastCompleted lastCompleted={detail.lastCompleted} />
      ) : null}
    </div>
  );
}

function WorkflowRow({ workflow }: { workflow: WorkflowDisplay }) {
  return (
    <div className="bulk-progress-workflow">
      <span className="bulk-progress-workflow-main">
        <span className="bulk-progress-workflow-prefix">{workflow.prefix}</span>
        <a
          className="bulk-progress-detail-link bulk-progress-workflow-title"
          href={workflow.url}
          target="_blank"
          rel="noopener noreferrer"
        >
          {workflow.title}
        </a>
      </span>
      {workflow.failedAt != null ? (
        <span className="bulk-progress-workflow-status">
          &middot; failed at {formatElapsed(workflow.failedAt)}
        </span>
      ) : null}
    </div>
  );
}

function LastCompleted({
  lastCompleted,
}: {
  lastCompleted: NonNullable<DetailDisplay["lastCompleted"]>;
}) {
  const { credits, runTimeSeconds, title, url } = lastCompleted;
  return (
    <div className="bulk-progress-last-completed">
      <span className="bulk-progress-last-completed-label">Last completed</span>
      <a
        className="bulk-progress-detail-link bulk-progress-last-completed-title"
        href={url}
        target="_blank"
        rel="noopener noreferrer"
      >
        {title}
      </a>
      {runTimeSeconds != null || credits != null ? (
        <span className="bulk-progress-last-completed-meta">
          {credits != null ? <> &middot; {formatCredits(credits)}</> : null}
          {runTimeSeconds != null ? (
            <> &middot; {formatElapsed(runTimeSeconds)}</>
          ) : null}
        </span>
      ) : null}
    </div>
  );
}
