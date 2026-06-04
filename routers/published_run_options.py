import typing

from fastapi import HTTPException, Query
from fastapi.responses import JSONResponse
from starlette.requests import Request

from daras_ai_v2.published_run_options import (
    get_published_run_options_page,
    get_selectable_workflow_page_cls,
)
from routers.custom_api_router import CustomAPIRouter

app = CustomAPIRouter()


@app.get("/__/published-run-options/")
def published_run_options(
    request: Request,
    page_slug: str,
    page: typing.Annotated[int, Query(ge=0)] = 0,
    include_root: bool = True,
    q: typing.Annotated[str | None, Query(max_length=100)] = None,
):
    try:
        page_cls = get_selectable_workflow_page_cls(page_slug)
    except KeyError:
        raise HTTPException(status_code=404)

    options, next_options_page = get_published_run_options_page(
        page_cls=page_cls,
        current_user=request.user,
        include_root=include_root,
        q=q,
        page=page,
    )
    return JSONResponse(
        {
            "options": [
                {"value": value, "label": label} for value, label in options.items()
            ],
            "nextOptionsPage": next_options_page,
        }
    )
