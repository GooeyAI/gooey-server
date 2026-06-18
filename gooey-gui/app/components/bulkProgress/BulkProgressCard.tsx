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
  rerun_all_key,
}: BulkProgressCardProps) {
  const liveElapsedSeconds = useLiveElapsedSeconds(
    snapshot.elapsed_seconds,
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
          <SummaryStat label="Rows" value={model.totalRows}>
            {model.rowsCaption}
          </SummaryStat>
          <SummaryStat label="Credits" value={model.credits}>
            {model.averageCredits}
          </SummaryStat>
          <SummaryStat label="Total time" value={model.totalTime}>
            {model.averageRunTime}
          </SummaryStat>
        </div>
        <RerunAllActions
          rerunAllKey={rerun_all_key}
          showRerun={model.showRerun}
        />
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
                {model.marker === "dot" && (
                  <span className="bulk-progress-dot" />
                )}
                <strong>{model.title}</strong>
              </div>
              <div className="bulk-progress-headline">{model.headline}</div>
              <MetaRow parts={model.metaParts} />
            </div>
          </div>
        </div>
      </div>
      {model.detail ? <ProgressDetail detail={model.detail} /> : null}
      <RerunAllActions
        rerunAllKey={rerun_all_key}
        showRerun={model.showRerun}
      />
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

const RING_RADIUS = 40;

function ProgressRing({
  ringPercent,
  ringLabel,
}: {
  ringPercent: number;
  ringLabel: string;
}) {
  const circumference = 2 * Math.PI * RING_RADIUS;
  const boundedRingPercent = Math.max(Math.min(ringPercent, 100), 0);
  const remaining = circumference - (circumference * boundedRingPercent) / 100;

  return (
    <div className="bulk-progress-ring">
      <svg viewBox="0 0 100 100" aria-hidden="true">
        <circle
          className="bulk-progress-ring-track"
          cx="50"
          cy="50"
          r={RING_RADIUS}
        />
        <circle
          className="bulk-progress-ring-bar"
          cx="50"
          cy="50"
          r={RING_RADIUS}
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
  return (
    <div className="bulk-progress-meta">
      {parts.map((part, index) => (
        <span className="bulk-progress-meta-item" key={index}>
          {part}
        </span>
      ))}
    </div>
  );
}

function ProgressDetail({ detail }: { detail: DetailDisplay }) {
  let inputAudioSafeHref: string | null = null;
  if (detail.inputAudioUrl) {
    try {
      const parsed = new URL(detail.inputAudioUrl);
      if (parsed.protocol === "http:" || parsed.protocol === "https:") {
        inputAudioSafeHref = parsed.href;
      }
    } catch {
      inputAudioSafeHref = null;
    }
  }

  return (
    <div className="bulk-progress-detail">
      <div className="bulk-progress-current">
        <strong>{detail.rowLabel}</strong>
      </div>
      {detail.showStoppingMessage ? (
        <div className="bulk-progress-stop-pending">
          Canceling this run, this may take a moment.
        </div>
      ) : null}
      {detail.workflow ? (
        <WorkflowRow
          key={`${detail.rowLabel}:${detail.workflow.url}`}
          workflow={detail.workflow}
        />
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
          {inputAudioSafeHref ? (
            <a
              href={inputAudioSafeHref}
              target="_blank"
              rel="noopener noreferrer"
            >
              View audio &rarr;
            </a>
          ) : (
            <span>{detail.inputAudioUrl}</span>
          )}
        </div>
      ) : null}
      {detail.lastCompleted ? (
        <LastCompleted lastCompleted={detail.lastCompleted} />
      ) : null}
    </div>
  );
}

function WorkflowRow({ workflow }: { workflow: WorkflowDisplay }) {
  const showElapsed = workflow.elapsedSeconds != null;
  const liveElapsedSeconds = useLiveElapsedSeconds(
    workflow.elapsedSeconds ?? 0,
    showElapsed
  );

  return (
    <div className="bulk-progress-workflow">
      <span className="bulk-progress-workflow-main">
        <span className="bulk-progress-workflow-prefix">{workflow.prefix}</span>
        <span className="bulk-progress-workflow-link-group">
          <a
            className="bulk-progress-detail-link bulk-progress-workflow-title"
            href={workflow.url}
            target="_blank"
            rel="noopener noreferrer"
          >
            {workflow.title}
          </a>
          {showElapsed ? (
            <span className="bulk-progress-workflow-elapsed">
              {formatElapsed(liveElapsedSeconds ?? 0)}
            </span>
          ) : null}
        </span>
      </span>
      {workflow.failedAt != null ? (
        <span className="bulk-progress-workflow-status">
          failed at {formatElapsed(workflow.failedAt)}
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
      <span className="bulk-progress-workflow-link-group">
        <a
          className="bulk-progress-detail-link bulk-progress-workflow-title"
          href={url}
          target="_blank"
          rel="noopener noreferrer"
        >
          {title}
        </a>
        {credits != null ? (
          <span className="bulk-progress-workflow-elapsed">
            {formatCredits(credits)}
          </span>
        ) : null}
        {runTimeSeconds != null ? (
          <span className="bulk-progress-workflow-elapsed">
            {formatElapsed(runTimeSeconds)}
          </span>
        ) : null}
      </span>
    </div>
  );
}
