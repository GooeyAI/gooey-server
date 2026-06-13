export type {
  BulkProgressCardProps,
  BulkProgressSnapshot,
  BulkRunnerRunState,
} from "./generated/componentProps";

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
  inputPrompt?: string | null;
  inputAudioUrl?: string | null;
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
