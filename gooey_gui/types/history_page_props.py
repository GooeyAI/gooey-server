from __future__ import annotations

import pydantic

from gooey_gui.types.home_page_props import WorkflowCardData


class SurfaceTabData(pydantic.BaseModel):
    id: str
    title: str
    icon: str | None = None
    href: str
    active: bool = False


class WorkflowFilterOption(pydantic.BaseModel):
    id: str
    title: str
    href: str
    active: bool = False


class OwnerFilterOption(pydantic.BaseModel):
    """ "Just me" vs the whole workspace."""

    id: str
    label: str
    icon_html: str
    href: str
    active: bool = False


class HistoryPageProps(pydantic.BaseModel):
    _component: str = "HistoryPage"

    title: str = "History"
    # "Just me" vs the whole workspace - same shape as the surface tabs
    owner_options: list[SurfaceTabData] = []
    workflow_options: list[WorkflowFilterOption] = []
    surface_tabs: list[SurfaceTabData] = []
    cards: list[WorkflowCardData] = []
    load_more_href: str | None = None
    empty_message: str | None = None
