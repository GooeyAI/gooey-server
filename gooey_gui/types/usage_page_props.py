from __future__ import annotations

import pydantic

from gooey_gui.types.home_page_props import WorkflowCardData


class UsagePageProps(pydantic.BaseModel):
    _component: str = "UsagePage"

    cards: list[WorkflowCardData] = []
    load_more_href: str | None = None
    empty_message: str = "No usage yet."
