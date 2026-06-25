import gooey_gui as gui
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from daras_ai_v2.meta_content import raw_build_meta_tags
from memory.models import MemoryEntry
from memory.widgets import manage_memory_table
from routers.custom_api_router import CustomAPIRouter
from routers.root import get_og_url_path
from workspaces.widgets import get_current_workspace

app = CustomAPIRouter()


@gui.route(app, "/account/memory/")
def memory_route(request: Request):
    # imported lazily to avoid a circular import: routers.account builds its
    # AccountTabs enum from memory_route, while this page renders inside the
    # shared account tabs wrapper.
    from routers.account import AccountTabs, account_page_wrapper

    with account_page_wrapper(request, AccountTabs.memory) as workspace:
        manage_memory_table(request, workspace=workspace)

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


@app.post("/__/memory/delete/")
def delete_memory_entry(request: Request, body: DeleteMemoryEntryRequest):
    if not request.user or request.user.is_anonymous:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    workspace = get_current_workspace(request.user, request.session)
    num_deleted = MemoryEntry.objects.filter(
        user_id=body.user_id, key=body.key, workspace=workspace
    ).delete()[0]
    if not num_deleted:
        return JSONResponse({"error": "Not found"}, status_code=404)

    return {"success": True}
