from __future__ import annotations

import pydantic

from gooey_gui.types.home_page_props import WorkflowCardData


class RunGridProps(pydantic.BaseModel):
    """A page of run cards."""

    _component: str = "RunGrid"

    cards: list[WorkflowCardData] = []
    load_more_href: str | None = None
    empty_message: str = "Nothing here yet."
