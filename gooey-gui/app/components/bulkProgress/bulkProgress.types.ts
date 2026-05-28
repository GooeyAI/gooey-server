// Keep in sync with widgets/bulk_progress_display.py (BulkProgressSnapshot).

export type BulkRunnerRunState =
  | "running"
  | "stopping"
  | "evaluating"
  | "complete"
  | "error"
  | "stopped";

export type BulkProgressSnapshot = {
  runState: BulkRunnerRunState;
  elapsedSeconds?: number | null;
  completedUnitRuns: number;
  totalUnitRuns: number;
  totalRows: number;
  currentRowNumber: number;
  currentWorkflowNumber: number;
  totalWorkflows: number;
  currentWorkflowTitle: string;
  currentWorkflowUrl: string;
  currentWorkflowRunTimeSeconds?: number | null;
  creditsUsed?: number | null;
  totalEvalRuns?: number;
  evalCurrent?: number;
  evalTotal?: number;
  evalWorkflowTitle?: string;
  inputPrompt?: string;
  inputAudioUrl?: string;
  lastCompletedWorkflowTitle?: string;
  lastCompletedWorkflowUrl?: string;
  lastCompletedRunTimeSeconds?: number | null;
  lastCompletedCredits?: number | null;
};

export type BulkProgressCardProps = {
  snapshot: BulkProgressSnapshot;
  rerunAllKey?: string | null;
};

export type WorkflowDisplay = {
  prefix: string;
  title: string;
  url: string;
  failedAt: number | null;
  elapsedSeconds: number | null;
};

export type DetailDisplay = {
  rowLabel: string;
  showStoppingMessage: boolean;
  workflow: WorkflowDisplay | null;
  inputPrompt?: string;
  inputAudioUrl?: string;
  lastCompleted?: {
    title: string;
    url: string;
    credits?: number | null;
    runTimeSeconds?: number | null;
  };
};

export type CompleteCardModel = {
  kind: "complete";
  title: string;
  totalRuns: number;
  totalRows: number;
  rowsCaption: string;
  totalTime: string;
  averageRunTime: string;
  credits: string;
  averageCredits: string;
  showRerun: boolean;
};

export type ActiveCardModel = {
  kind: "active";
  cardClass: string;
  title: string;
  headline: string;
  metaParts: string[];
  marker: "dot" | "stop" | null;
  ringPercent: number;
  ringLabel: string;
  ringAccent: string;
  detail: DetailDisplay | null;
  showRerun: boolean;
};

export type CardModel = CompleteCardModel | ActiveCardModel;
