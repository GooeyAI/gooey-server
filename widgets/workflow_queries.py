from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from django.db.models import F, OuterRef, Q, Subquery
from starlette.requests import Request

from bots.models import PublishedRun, PublishedRunVersion, SavedRun
from daras_ai_v2.fastapi_tricks import fastapi_login_required
from routers.custom_api_router import CustomAPIRouter
from workspaces.widgets import get_current_workspace

if TYPE_CHECKING:
    from app_users.models import AppUser
    from workspaces.models import Workspace

router = CustomAPIRouter()

SAVED_WORKFLOW_LIST_LIMIT = 3
RECENT_WORKFLOW_SCAN_LIMIT = 200


@router.post("/__/workflows/recent/", dependencies=[fastapi_login_required])
def recent_workflow_items(request: Request):
    # Imported lazily because navigation_sidebar imports this endpoint to build
    # its URL.
    from widgets.navigation_sidebar import load_recent_workflow_items

    workspace = get_current_workspace(request.user, request.session)
    items = load_recent_workflow_items(request.user, workspace)
    return {"items": [item.model_dump() for item in items]}


def saved_published_runs(
    user: AppUser | None,
    workspace: Workspace | None,
    limit: int = SAVED_WORKFLOW_LIST_LIMIT,
) -> list[PublishedRun]:
    if user is None or workspace is None:
        return []
    pr_filter = Q(workspace=workspace)
    if workspace.is_personal:
        pr_filter |= Q(created_by=user)
    latest_change_notes = (
        PublishedRunVersion.objects.filter(published_run=OuterRef("pk"))
        .order_by("-created_at")
        .values("change_notes")[:1]
    )
    return list(
        PublishedRun.objects.filter(pr_filter)
        .select_related("last_edited_by", "saved_run", "workspace", "workflow_metadata")
        .annotate(latest_change_notes=Subquery(latest_change_notes))
        .order_by("-updated_at")[:limit]
    )


def recent_run_ids(
    user: AppUser | None,
    workspace: Workspace | None,
    limit: int,
    *,
    include_builder_runs: bool,
) -> list[int]:
    if user is None or workspace is None:
        return []

    history_runs = (
        SavedRun.objects.filter(
            uid=user.uid, workspace=workspace, surface=SavedRun.Surface.run
        )
        .annotate(published_run_id=F("parent_version__published_run_id"))
        .order_by("-updated_at")
        .values("id", "published_run_id", "updated_at")[:RECENT_WORKFLOW_SCAN_LIMIT]
    )
    builder_runs = []
    if include_builder_runs:
        # workflow runs the builder produced (shown on their workflow page)
        builder_child_runs = (
            SavedRun.objects.filter(
                uid=user.uid,
                workspace=workspace,
                surface=SavedRun.Surface.builder_child,
                parent_builder_saved_run__thread_as_last_run__isnull=False,
            )
            .order_by("-updated_at")
            .values("id", "updated_at")[:limit]
        )
        # /new page builder runs
        builder_prompt_runs = (
            SavedRun.objects.filter(
                uid=user.uid,
                workspace=workspace,
                surface=SavedRun.Surface.builder_prompt,
                thread_as_last_run__isnull=False,
                child_builder_saved_runs__isnull=True,
            )
            .order_by("-updated_at")
            .values("id", "updated_at")[:limit]
        )
        builder_runs = list(builder_child_runs) + list(builder_prompt_runs)

    return _merge_recent_run_ids(history_runs, builder_runs, limit)


def _merge_recent_run_ids(
    history_runs: Iterable[dict[str, Any]],
    builder_runs: Iterable[dict[str, Any]],
    limit: int,
) -> list[int]:
    picked: list[tuple[Any, int]] = []
    seen_published_runs: set[int | None] = set()
    for row in history_runs:
        if row["published_run_id"] in seen_published_runs:
            continue
        seen_published_runs.add(row["published_run_id"])
        picked.append((row["updated_at"], row["id"]))
        if len(picked) >= limit:
            break
    picked.extend((row["updated_at"], row["id"]) for row in builder_runs)

    picked.sort(key=lambda row: row[0], reverse=True)
    return [id_ for _, id_ in picked[:limit]]


# What counts as somebody using a published app: an end user over an integration,
# somebody opening the app and pressing Run, or an API caller. Deliberately not
# the machinery a run spawns (tool_call, internal, analysis, export) nor the
# builder runs from authoring the app - those are the owner at work, not usage,
# and they'd inflate any count built on top of this.
USAGE_SURFACES = [
    SavedRun.Surface.deployment,
    SavedRun.Surface.run,
    SavedRun.Surface.api,
]


def usage_runs(
    *,
    workflow: int,
    workspace: Workspace,
    published_run: PublishedRun,
):
    """Every run one published app produced, whoever triggered it.

    The subject is the app, not the recipe: two copilots in a workspace share a
    workflow, so filtering on `workflow` alone pools their runs together.
    """
    return SavedRun.objects.filter(
        # redundant against the published run, which pins one workflow, but it
        # heads the ["workflow", "workspace", "-updated_at"] index this list is
        # ordered by
        workflow=workflow,
        # not redundant: the root published run parents every playground run on
        # the platform, so this is what keeps a root-pr Usage tab to one workspace
        workspace=workspace,
        parent_version__published_run=published_run,
        surface__in=USAGE_SURFACES,
    )
