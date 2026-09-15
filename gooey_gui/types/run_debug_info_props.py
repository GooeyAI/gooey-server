from __future__ import annotations

from pydantic import BaseModel

from gooey_gui.types.run_timeline_props import RunTimelineProps


class AuthorProps(BaseModel):
    name: str
    photo_url: str | None = None
    url: str | None = None


class DebugSource(BaseModel):
    """The platform a bot run came in on, and the masked end user it was for."""

    icon_html: str
    title: str
    sender: str | None = None


class RunDebugInfoProps(BaseModel):
    """The run metadata block at the top of the v2 Debug pane, with the timeline below it."""

    _component: str = "RunDebugInfo"

    timeline: RunTimelineProps
    source: DebugSource | None = None
    conversation_title: str | None = None
    conversation_url: str | None = None
    run_by: AuthorProps | None = None
    charged_to: AuthorProps | None = None
    parent_run_url: str | None = None
