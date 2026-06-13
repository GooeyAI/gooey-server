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
  const totalRuns = snapshot.totalUnitRuns + (snapshot.totalEvalRuns || 0);
  if (snapshot.creditsUsed == null || totalRuns <= 0) {
    return "-";
  }
  return `${(snapshot.creditsUsed / totalRuns).toFixed(1)} Cr / run`;
}

export function formatAverageRunTime(snapshot: BulkProgressSnapshot) {
  if (snapshot.elapsedSeconds == null || snapshot.totalUnitRuns <= 0) {
    return "-";
  }
  return `${(snapshot.elapsedSeconds / snapshot.totalUnitRuns).toFixed(
    1
  )}s avg / run`;
}
