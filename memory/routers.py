from __future__ import annotations

from fastapi.requests import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import gooey_gui as gui
from daras_ai_v2.fastapi_tricks import fastapi_login_required
from daras_ai_v2.meta_content import raw_build_meta_tags
from functions.models import FunctionScopes
from memory.models import MemoryEntry
from memory.widgets import (
    MEMORY_DELETE_URL,
    MEMORY_FILTER_OPTIONS_URL,
    MemoryFilterFieldName,
    get_memory_filter_options,
    manage_memory_table,
)
from routers.custom_api_router import CustomAPIRouter
from routers.root import get_og_url_path
from workspaces.widgets import get_current_workspace


app = CustomAPIRouter()


@gui.route(app, "/account/memory/")
def memory_route(
    request: Request,
    scope: str | None = None,
    member: str | None = None,
    saved_workflow: str | None = None,
    platform_user: str = "",
    deployment: str | None = None,
    conversation: str | None = None,
    search: str = "",
):
    # imported lazily to avoid a circular import: routers.account builds its
    # AccountTabs enum from memory_route, while this page renders inside the
    # shared account tabs wrapper.
    from routers.account import AccountTabs, account_page_wrapper
    from routers.bots_api import get_api_hashid_or_404
    from app_users.models import AppUser
    from bots.models import BotIntegration, Conversation, PublishedRun

    with account_page_wrapper(request, AccountTabs.memory) as workspace:
        manage_memory_table(
            request,
            workspace=workspace,
            scope=(FunctionScopes.get(scope) if scope else None),
            member=(get_api_hashid_or_404(AppUser, member) if member else None),
            saved_workflow=(
                get_api_hashid_or_404(PublishedRun, saved_workflow)
                if saved_workflow
                else None
            ),
            platform_user=platform_user,
            deployment=(
                get_api_hashid_or_404(BotIntegration, deployment)
                if deployment
                else None
            ),
            conversation=(
                get_api_hashid_or_404(Conversation, conversation)
                if conversation
                else None
            ),
            search=search,
        )

    url = get_og_url_path(request)
    return dict(
        meta=raw_build_meta_tags(
            url=url,
            canonical_url=url,
            title="Memory • Gooey.AI",
            description="Your Gooey Memory entries.",
            robots="noindex,nofollow",
        )
    )


class DeleteMemoryEntryRequest(BaseModel):
    user_id: str
    key: str


@app.post(MEMORY_DELETE_URL, dependencies=[fastapi_login_required])
def delete_memory_entry(request: Request, body: DeleteMemoryEntryRequest):
    workspace = get_current_workspace(request.user, request.session)
    num_deleted = MemoryEntry.objects.filter(
        user_id=body.user_id, key=body.key, workspace=workspace
    ).delete()[0]
    if not num_deleted:
        return JSONResponse({"error": "Not found"}, status_code=404)

    return {"success": True}


class MemoryFilterOptionsRequest(BaseModel):
    field: MemoryFilterFieldName
    search: str = ""


@app.post(MEMORY_FILTER_OPTIONS_URL, dependencies=[fastapi_login_required])
def memory_filter_options(request: Request, body: MemoryFilterOptionsRequest):
    workspace = get_current_workspace(request.user, request.session)
    options = get_memory_filter_options(
        workspace=workspace, field=body.field, search=body.search
    )
    return {"options": [option.model_dump() for option in options]}
