from enum import Enum

from pydantic import BaseModel, ConfigDict


class BulkRunnerRunState(str, Enum):
    running = "running"
    stopping = "stopping"
    evaluating = "evaluating"
    complete = "complete"
    error = "error"
    stopped = "stopped"


class BulkProgressSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runState: BulkRunnerRunState
    elapsedSeconds: float | None = None
    completedUnitRuns: int
    totalUnitRuns: int
    totalRows: int
    currentRowNumber: int
    currentWorkflowNumber: int
    totalWorkflows: int
    currentWorkflowTitle: str
    currentWorkflowUrl: str
    currentWorkflowRunTimeSeconds: float | None = None
    creditsUsed: int | None = None
    totalEvalRuns: int | None = None
    evalCurrent: int | None = None
    evalTotal: int | None = None
    evalWorkflowTitle: str | None = None
    inputPrompt: str | None = None
    inputAudioUrl: str | None = None
    lastCompletedWorkflowTitle: str | None = None
    lastCompletedWorkflowUrl: str | None = None
    lastCompletedRunTimeSeconds: float | None = None
    lastCompletedCredits: int | None = None


class BulkProgressCardProps(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot: BulkProgressSnapshot
    rerunAllKey: str | None = None
