from __future__ import annotations

import typing

import gooey_gui as gui
from django.contrib.humanize.templatetags.humanize import naturaltime
from fastapi.requests import Request
from furl import furl

from bots.models import PublishedRun
from daras_ai_v2.urls import paginate_queryset
from functions.models import FunctionScopes
from gooey_gui.types.workspace_memory_props import (
    MemoryEntryDetail,
    MemoryEntryRow,
    WorkspaceMemoryTableProps,
    MemoryScope,
)
from memory.models import MemoryEntry

if typing.TYPE_CHECKING:
    from workspaces.models import Workspace


def manage_memory_table(request: Request, workspace: Workspace):
    entries, cursor = paginate_workspace_memory(
        workspace=workspace,
        cursor=request.query_params,
    )

    next_page_url = None
    if cursor:
        next_url = furl(request.url).set(origin=None)
        next_url.query.params.update(cursor)
        next_page_url = str(next_url)

    if workspace.is_personal:
        description = (
            "Gooey Memory is a key-value store used by Functions and Copilot tools "
            "to persist data across runs. Entries scoped to your personal workspace "
            "are listed below."
        )
    else:
        description = (
            "Gooey Memory is a key-value store used by Functions and Copilot tools "
            "to persist data across runs. Entries scoped to "
            f"{workspace.display_name(request.user)} are listed below."
        )

    gui.model_component(
        WorkspaceMemoryTableProps(
            description=description,
            entries=[serialize_memory_entry(entry) for entry in entries],
            next_page_url=next_page_url,
            delete_url="/__/memory/delete/",
        )
    )


def serialize_memory_entry(entry: MemoryEntry) -> MemoryEntryRow:
    return MemoryEntryRow(
        user_id=entry.user_id,
        key=entry.key,
        value=entry.value,
        scope=MemoryScope(
            label=FunctionScopes.format_label(
                name=FunctionScopes.from_db(entry.scope).name,
                workspace=entry.workspace,
                user=entry.member,
                published_run=entry.saved_workflow,
            )
        ),
        details=build_memory_entry_details(entry),
        updated_at_label=str(naturaltime(entry.updated_at)),
    )


def build_memory_entry_details(entry: MemoryEntry) -> list[MemoryEntryDetail]:
    candidates = [
        (
            "fa-regular fa-buildings",
            "Workspace",
            entry.workspace and entry.workspace.display_name(),
        ),
        (
            "fa-solid fa-user",
            "Member",
            entry.member and entry.member.full_name(),
        ),
        (
            "fa-regular fa-floppy-disk",
            "Saved Workflow",
            entry.saved_workflow and str(entry.saved_workflow),
        ),
        (
            "fa-regular fa-user",
            "Platform User",
            entry.platform_user,
        ),
        (
            "fa-regular fa-robot",
            "Deployment",
            entry.deployment and str(entry.deployment),
        ),
        (
            "fa-regular fa-message",
            "Conversation",
            entry.conversation and entry.conversation.get_display_name(),
        ),
    ]
    return [
        MemoryEntryDetail(icon=icon, label=label, value=str(value))
        for icon, label, value in candidates
        if value
    ]


def paginate_workspace_memory(
    *,
    workspace: Workspace,
    cursor: dict[str, str],
    page_size: int = 50,
) -> tuple[list[MemoryEntry], dict[str, str] | None]:
    qs = MemoryEntry.objects.filter(workspace=workspace).select_related(
        "workspace",
        "workspace__created_by",
        "member",
        "saved_workflow",
        "deployment",
        "conversation",
    )
    return paginate_queryset(
        qs=qs,
        ordering=["-updated_at"],
        cursor=cursor,
        page_size=page_size,
    )


def get_memory_scope_published_run(
    published_run_id: str, workspace: Workspace
) -> PublishedRun | None:
    return PublishedRun.objects.filter(
        published_run_id=published_run_id, workspace=workspace
    ).first()
