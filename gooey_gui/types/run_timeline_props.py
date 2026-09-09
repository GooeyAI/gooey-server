from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RunTimelineProps(BaseModel):
    _component: str = "RunTimeline"

    created_at: datetime
    started_at: datetime
    finished_at: datetime
