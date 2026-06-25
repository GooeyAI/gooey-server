from __future__ import annotations

from typing import Any

import pydantic


class MemoryScope(pydantic.BaseModel):
    label: str


class MemoryEntryDetail(pydantic.BaseModel):
    icon: str
    value: str


class MemoryEntryRow(pydantic.BaseModel):
    user_id: str
    key: str
    # MemoryEntry.value is an arbitrary JSON value (string, number, object, ...).
    value: Any = pydantic.Field(default=None, json_schema_extra={"tsType": "unknown"})
    scope: MemoryScope
    details: list[MemoryEntryDetail]
    updated_at_label: str


class MemoryFilterOption(pydantic.BaseModel):
    value: str
    label: str
    # HTML icon markup (e.g. for scope options); plain text/FK options leave it unset.
    icon: str | None = None


class MemoryFilterField(pydantic.BaseModel):
    key: str
    label: str
    icon: str
    selected: MemoryFilterOption | None = None


class WorkspaceMemoryTableProps(pydantic.BaseModel):
    _component: str = "WorkspaceMemoryTable"

    description: str
    filters: list[MemoryFilterField]
    options_url: str
    search: str = ""
    entries: list[MemoryEntryRow]
    next_page_url: str | None = None
    delete_url: str
