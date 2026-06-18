import type { BulkProgressSnapshot } from "./bulkProgress.types";

export function formatElapsed(seconds: number) {
  if (seconds < 60) {
    return `${Math.round(seconds)}s`;
  }

  const roundedSeconds = Math.round(seconds) % 60;
  const totalMinutes = Math.floor(Math.round(seconds) / 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours) {
    return `${hours}h ${minutes}m`;
  }
  if (totalMinutes) {
    return `${totalMinutes}m ${roundedSeconds}s`;
  }
  return `${roundedSeconds}s`;
}

export function formatCredits(credits: number | null | undefined) {
  if (credits == null) {
    return "-";
  }
  return `${credits} Cr`;
}

export function formatAverageCredits(snapshot: BulkProgressSnapshot) {
  const totalRuns = snapshot.total_unit_runs + (snapshot.total_eval_runs || 0);
  if (snapshot.credits_used == null || totalRuns <= 0) {
    return "-";
  }
  return `${(snapshot.credits_used / totalRuns).toFixed(1)} Cr / run`;
}

export function formatAverageRunTime(snapshot: BulkProgressSnapshot) {
  if (snapshot.elapsed_seconds == null || snapshot.total_unit_runs <= 0) {
    return "-";
  }
  return `${(snapshot.elapsed_seconds / snapshot.total_unit_runs).toFixed(
    1
  )}s avg / run`;
}
