from __future__ import annotations

import typing

from bots.models.bot_integration import Platform
import gooey_gui as gui
from django.contrib.humanize.templatetags.humanize import naturaltime
from fastapi.requests import Request
from furl import furl

from bots.models import PublishedRun
from daras_ai_v2.urls import paginate_queryset
from functions.models import FunctionScopes, ScopeParts
from gooey_gui.types.workspace_memory_props import (
    MemoryEntryDetail,
    MemoryEntryRow,
    MemoryFilterField,
    MemoryFilterOption,
    WorkspaceMemoryTableProps,
    MemoryScope,
)
from memory.models import MemoryEntry
from django.db.models import Q

if typing.TYPE_CHECKING:
    from workspaces.models import Workspace
    from app_users.models import AppUser
    from bots.models import BotIntegration, Conversation, PublishedRun

MEMORY_FILTER_OPTIONS_URL = "/__/memory/filter-options/"
MEMORY_DELETE_URL = "/__/memory/delete/"


def manage_memory_table(
    request: Request,
    *,
    workspace: Workspace,
    scope: FunctionScopes | None,
    member: AppUser | None,
    saved_workflow: PublishedRun | None,
    platform_user: str,
    deployment: BotIntegration | None,
    conversation: Conversation | None,
    search: str,
):
    entries, cursor = paginate_workspace_memory(
        workspace=workspace,
        cursor=dict(request.query_params),
        scope=scope,
        member=member,
        saved_workflow=saved_workflow,
        platform_user=platform_user,
        deployment=deployment,
        conversation=conversation,
        search=search,
    )

    if cursor:
        next_url = furl(request.url).set(origin=None)
        next_url.query.params.update(cursor)
        next_page_url = str(next_url)
    else:
        next_page_url = None

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
            filters=list(
                build_memory_filter_fields(
                    scope=scope,
                    member=member,
                    saved_workflow=saved_workflow,
                    platform_user=platform_user,
                    deployment=deployment,
                    conversation=conversation,
                )
            ),
            options_url=MEMORY_FILTER_OPTIONS_URL,
            search=search,
            entries=[
                serialize_memory_entry(entry, workspace=workspace) for entry in entries
            ],
            next_page_url=next_page_url,
            delete_url=MEMORY_DELETE_URL,
        )
    )


def paginate_workspace_memory(
    *,
    workspace: Workspace,
    cursor: dict[str, str],
    scope: FunctionScopes | None,
    member: AppUser | None,
    saved_workflow: PublishedRun | None,
    platform_user: str,
    deployment: BotIntegration | None,
    conversation: Conversation | None,
    search: str = "",
    page_size: int = 50,
) -> tuple[list[MemoryEntry], dict[str, str] | None]:
    qs = MemoryEntry.objects.select_related(
        "member",
        "saved_workflow",
        "deployment",
        "conversation",
    ).filter(workspace=workspace)
    if search:
        qs = qs.filter(key__icontains=search)
    if scope:
        qs = qs.filter(scope=scope.db_value)
    if member:
        qs = qs.filter(member=member)
    if saved_workflow:
        qs = qs.filter(saved_workflow=saved_workflow)
    if platform_user:
        qs = qs.filter(platform_user=platform_user)
    if deployment:
        qs = qs.filter(deployment=deployment)
    if conversation:
        qs = qs.filter(conversation=conversation)
    return paginate_queryset(
        qs=qs,
        ordering=["-updated_at"],
        cursor=cursor,
        page_size=page_size,
    )


def serialize_memory_entry(
    entry: MemoryEntry, *, workspace: Workspace
) -> MemoryEntryRow:
    return MemoryEntryRow(
        user_id=entry.user_id,
        key=entry.key,
        value=entry.value,
        scope=MemoryScope(
            label=FunctionScopes.format_label(
                name=(
                    FunctionScopes.from_db(entry.scope).name if entry.scope else None
                ),
                workspace=workspace,
                user=entry.member,
                published_run=entry.saved_workflow,
            )
        ),
        details=list(build_memory_entry_details(entry)),
        updated_at_label=str(naturaltime(entry.updated_at)),
    )


def build_memory_entry_details(
    entry: MemoryEntry,
) -> typing.Iterator[MemoryEntryDetail]:
    if entry.member:
        yield MemoryEntryDetail(
            icon=ScopeParts.member.icon,
            value=MemberFilter.get_display(entry.member),
        )
    if entry.saved_workflow:
        yield MemoryEntryDetail(
            icon=ScopeParts.saved_workflow.icon,
            value=SavedWorkflowFilter.get_display(entry.saved_workflow),
        )
    if entry.platform_user:
        yield MemoryEntryDetail(
            icon=ScopeParts.platform_user.icon,
            value=PlatformUserFilter.get_display(entry.platform_user),
        )
    if entry.deployment:
        yield MemoryEntryDetail(
            icon=Platform(entry.deployment.platform).get_icon(),
            value=DeploymentFilter.get_display(entry.deployment),
        )
    if entry.conversation:
        yield MemoryEntryDetail(
            icon=ScopeParts.conversation.icon,
            value=ConversationFilter.get_display(entry.conversation),
        )


def build_memory_filter_fields(
    *,
    scope: FunctionScopes | None,
    member: AppUser | None,
    saved_workflow: PublishedRun | None,
    platform_user: str,
    deployment: BotIntegration | None,
    conversation: Conversation | None,
) -> typing.Iterator[MemoryFilterField]:
    yield MemoryFilterField(
        key="scope",
        label="Scope",
        icon='<i class="fa-regular fa-bullseye"></i>',
        selected=(
            MemoryFilterOption(value=scope.name, label=scope.label, icon=scope.icon)
            if scope
            else None
        ),
    )
    yield MemoryFilterField(
        key=ScopeParts.member.name,
        label=ScopeParts.member.label,
        icon=ScopeParts.member.icon,
        selected=(MemberFilter.get_filter_option(member) if member else None),
    )
    yield MemoryFilterField(
        key=ScopeParts.saved_workflow.name,
        label=ScopeParts.saved_workflow.label,
        icon=ScopeParts.saved_workflow.icon,
        selected=(
            SavedWorkflowFilter.get_filter_option(saved_workflow)
            if saved_workflow
            else None
        ),
    )
    yield MemoryFilterField(
        key=ScopeParts.platform_user.name,
        label=ScopeParts.platform_user.label,
        icon=ScopeParts.platform_user.icon,
        selected=(
            PlatformUserFilter.get_filter_option(platform_user)
            if platform_user
            else None
        ),
    )
    yield MemoryFilterField(
        key=ScopeParts.deployment.name,
        label=ScopeParts.deployment.label,
        icon=ScopeParts.deployment.icon,
        selected=(
            DeploymentFilter.get_filter_option(deployment) if deployment else None
        ),
    )
    yield MemoryFilterField(
        key=ScopeParts.conversation.name,
        label=ScopeParts.conversation.label,
        icon=ScopeParts.conversation.icon,
        selected=(
            ConversationFilter.get_filter_option(conversation) if conversation else None
        ),
    )


MemoryFilterFieldName = typing.Literal[
    "scope", "member", "saved_workflow", "platform_user", "deployment", "conversation"
]


def get_memory_filter_options(
    *,
    workspace: Workspace,
    field: MemoryFilterFieldName,
    search: str = "",
    limit: int = 20,
) -> list[MemoryFilterOption]:
    match field:
        case "scope":
            return [
                MemoryFilterOption(
                    value=scope.name,
                    label=scope.label,
                    icon=scope.icon,
                )
                for scope in FunctionScopes
            ]
        case ScopeParts.member.name:
            return [
                MemberFilter.get_filter_option(member)
                for member in MemberFilter.get_qs(workspace, search).distinct()[:limit]
            ]
        case ScopeParts.saved_workflow.name:
            return [
                SavedWorkflowFilter.get_filter_option(saved_workflow)
                for saved_workflow in SavedWorkflowFilter.get_qs(
                    workspace, search
                ).distinct()[:limit]
            ]
        case ScopeParts.platform_user.name:
            return [
                PlatformUserFilter.get_filter_option(platform_user)
                for platform_user in PlatformUserFilter.get_qs(
                    workspace, search
                ).distinct()[:limit]
            ]
        case ScopeParts.deployment.name:
            return [
                DeploymentFilter.get_filter_option(deployment)
                for deployment in DeploymentFilter.get_qs(workspace, search).distinct()[
                    :limit
                ]
            ]
        case ScopeParts.conversation.name:
            return [
                ConversationFilter.get_filter_option(conversation)
                for conversation in ConversationFilter.get_qs(
                    workspace, search
                ).distinct()[:limit]
            ]
    return []


class MemberFilter:
    @staticmethod
    def get_filter_option(member: AppUser) -> MemoryFilterOption:
        from routers.bots_api import api_hashids

        return MemoryFilterOption(
            value=api_hashids.encode(member.id),
            label=MemberFilter.get_display(member),
        )

    @staticmethod
    def get_qs(workspace: Workspace, search: str = ""):
        from app_users.models import AppUser

        return AppUser.objects.filter(memory_entries__workspace=workspace).filter(
            Q(display_name__icontains=search) | Q(email__icontains=search)
        )

    @staticmethod
    def get_display(member: AppUser) -> str:
        return str(member.full_name())


class SavedWorkflowFilter:
    @staticmethod
    def get_filter_option(saved_workflow: PublishedRun) -> MemoryFilterOption:
        from routers.bots_api import api_hashids

        return MemoryFilterOption(
            value=api_hashids.encode(saved_workflow.id),
            label=SavedWorkflowFilter.get_display(saved_workflow),
        )

    @staticmethod
    def get_qs(workspace: Workspace, search: str = ""):
        from bots.models import PublishedRun

        return PublishedRun.objects.filter(memory_entries__workspace=workspace).filter(
            Q(title__icontains=search)
        )

    @staticmethod
    def get_display(saved_workflow: PublishedRun) -> str:
        return str(saved_workflow)


class PlatformUserFilter:
    @staticmethod
    def get_filter_option(platform_user: str) -> MemoryFilterOption:
        return MemoryFilterOption(
            value=platform_user,
            label=PlatformUserFilter.get_display(platform_user),
        )

    @staticmethod
    def get_qs(workspace: Workspace, search: str = ""):
        return (
            MemoryEntry.objects.filter(workspace=workspace)
            .exclude(platform_user="")
            .filter(Q(platform_user__icontains=search))
            .values_list("platform_user", flat=True)
        )

    @staticmethod
    def get_display(platform_user: str) -> str:
        return str(platform_user)


class DeploymentFilter:
    @staticmethod
    def get_filter_option(deployment: BotIntegration) -> MemoryFilterOption:
        from routers.bots_api import api_hashids

        return MemoryFilterOption(
            value=api_hashids.encode(deployment.id),
            label=DeploymentFilter.get_display(deployment),
            icon=Platform(deployment.platform).get_icon(),
        )

    @staticmethod
    def get_qs(workspace: Workspace, search: str = ""):
        from bots.models import BotIntegration

        return BotIntegration.objects.filter(
            memory_entries__workspace=workspace
        ).filter(name__icontains=search)

    @staticmethod
    def get_display(deployment: BotIntegration) -> str:
        return str(deployment)


class ConversationFilter:
    @staticmethod
    def get_filter_option(conversation: Conversation) -> MemoryFilterOption:
        from routers.bots_api import api_hashids

        return MemoryFilterOption(
            value=api_hashids.encode(conversation.id),
            label=ConversationFilter.get_display(conversation),
        )

    @staticmethod
    def get_qs(workspace: Workspace, search: str = ""):
        from bots.models import Conversation

        query = Q()
        for field in Conversation.user_id_fields:
            query |= Q(**{f"{field}__icontains": search})
        return Conversation.objects.filter(memory_entries__workspace=workspace).filter(
            query
        )

    @staticmethod
    def get_display(conversation: Conversation) -> str:
        return str(conversation.get_display_name())
