import datetime
import json
import os
import os.path
import os.path
import typing
from types import SimpleNamespace

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Form
from fastapi import HTTPException
from fastapi import Response
from furl import furl
from pydantic import BaseModel, Field
from pydantic import ValidationError
from pydantic import create_model
from pydantic.generics import GenericModel
from starlette.datastructures import FormData
from starlette.datastructures import UploadFile
from starlette.requests import Request

import gooey_ui as st
from app_users.models import AppUser
from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2 import settings
from daras_ai_v2.all_pages import all_api_pages
from daras_ai_v2.base import (
    BasePage,
    StateKeys,
)
from gooey_token_authentication1.token_authentication import api_auth_header

app = APIRouter()


O = typing.TypeVar("O")

## v2


class ApiResponseModelV2(GenericModel, typing.Generic[O]):
    id: str = Field(description="Unique ID for this run")
    url: str = Field(description="Web URL for this run")
    created_at: str = Field(description="Time when the run was created as ISO format")

    output: O = Field(description="Output of the run")


class FailedResponseDetail(BaseModel):
    id: str | None = Field(description="Unique ID for this run")
    url: str | None = Field(description="Web URL for this run")
    created_at: str | None = Field(
        description="Time when the run was created as ISO format"
    )

    error: str | None = Field(description="Error message if the run failed")


class FailedReponseModelV2(BaseModel):
    detail: FailedResponseDetail


## v3


class BaseResponseModelV3(GenericModel):
    run_id: str = Field(description="Unique ID for this run")
    web_url: str = Field(description="Web URL for this run")
    created_at: str = Field(description="Time when the run was created as ISO format")


class AsyncApiResponseModelV3(BaseResponseModelV3):
    status_url: str = Field(
        description="URL to check the status of the run. Also included in the `Location` header of the response."
    )


class AsyncStatusResponseModelV3(BaseResponseModelV3, typing.Generic[O]):
    run_time_sec: int = Field(description="Total run time in seconds")
    status: typing.Literal["starting", "running", "completed", "failed"] = Field(
        description="Status of the run"
    )
    detail: str = Field(
        description="Details about the status of the run as a human readable string"
    )
    output: O | None = Field(
        description='Output of the run. Only available if status is `"completed"`'
    )


async def request_form_files(request: Request) -> FormData:
    return await request.form()


def script_to_api(page_cls: typing.Type[BasePage]):
    endpoint = page_cls().endpoint.rstrip("/")
    response_model = create_model(
        page_cls.__name__ + "Response",
        __base__=ApiResponseModelV2[page_cls.ResponseModel],
    )

    @app.post(
        os.path.join(endpoint, ""),
        response_model=response_model,
        responses={500: {"model": FailedReponseModelV2}, 402: {}},
        operation_id=page_cls.slug_versions[0],
        name=page_cls.title + " (v2 sync)",
    )
    @app.post(
        endpoint,
        response_model=response_model,
        responses={500: {"model": FailedReponseModelV2}, 402: {}},
        include_in_schema=False,
    )
    def run_api_json(
        request: Request,
        page_request: page_cls.RequestModel,
        user: AppUser = Depends(api_auth_header),
    ):
        return call_api(
            page_cls=page_cls,
            user=user,
            request_body=page_request.dict(),
            query_params=request.query_params,
        )

    @app.post(
        os.path.join(endpoint, "form/"),
        response_model=response_model,
        responses={500: {"model": FailedReponseModelV2}, 402: {}},
        include_in_schema=False,
    )
    @app.post(
        os.path.join(endpoint, "form"),
        response_model=response_model,
        responses={500: {"model": FailedReponseModelV2}, 402: {}},
        include_in_schema=False,
    )
    def run_api_form(
        request: Request,
        user: AppUser = Depends(api_auth_header),
        form_data=Depends(request_form_files),
        page_request_json: str = Form(alias="json"),
    ):
        # parse form data
        page_request = _parse_form_data(page_cls, form_data, page_request_json)
        # call regular json api
        return run_api_json(request, page_request=page_request, user=user)

    endpoint = endpoint.replace("v2", "v3")
    response_model = AsyncApiResponseModelV3

    @app.post(
        os.path.join(endpoint, "async/"),
        response_model=response_model,
        responses={402: {}},
        operation_id="async__" + page_cls.slug_versions[0],
        name=page_cls.title + " (v3 async)",
        status_code=202,
    )
    @app.post(
        os.path.join(endpoint, "async"),
        response_model=response_model,
        responses={402: {}},
        include_in_schema=False,
        status_code=202,
    )
    def run_api_json_async(
        request: Request,
        response: Response,
        page_request: page_cls.RequestModel,
        user: AppUser = Depends(api_auth_header),
    ):
        ret = call_api(
            page_cls=page_cls,
            user=user,
            request_body=page_request.dict(),
            query_params=request.query_params,
            run_async=True,
        )
        response.headers["Location"] = ret["status_url"]
        return ret

    @app.post(
        os.path.join(endpoint, "async/form/"),
        response_model=response_model,
        responses={402: {}},
        include_in_schema=False,
    )
    @app.post(
        os.path.join(endpoint, "async/form"),
        response_model=response_model,
        responses={402: {}},
        include_in_schema=False,
    )
    def run_api_form(
        request: Request,
        response: Response,
        user: AppUser = Depends(api_auth_header),
        form_data=Depends(request_form_files),
        page_request_json: str = Form(alias="json"),
    ):
        # parse form data
        page_request = _parse_form_data(page_cls, form_data, page_request_json)
        # call regular json api
        return run_api_json_async(
            request, response=response, page_request=page_request, user=user
        )

    response_model = create_model(
        page_cls.__name__ + "StatusResponse",
        __base__=AsyncStatusResponseModelV3[page_cls.ResponseModel],
    )

    @app.get(
        os.path.join(endpoint, "status/"),
        response_model=response_model,
        responses={402: {}},
        operation_id="status__" + page_cls.slug_versions[0],
        name=page_cls.title + " (v3 status)",
    )
    @app.get(
        os.path.join(endpoint, "status"),
        response_model=response_model,
        responses={402: {}},
        include_in_schema=False,
    )
    def get_run_status(
        run_id: str,
        user: AppUser = Depends(api_auth_header),
    ):
        self = page_cls()
        sr = self.get_current_doc_sr(example_id=None, run_id=run_id, uid=user.uid)
        state = sr.to_dict()
        err_msg = state.get(StateKeys.error_msg)
        run_time = state.get(StateKeys.run_time, 0)
        web_url = str(furl(self.app_url(run_id=run_id, uid=user.uid)))
        ret = {
            "run_id": run_id,
            "web_url": web_url,
            "created_at": sr.created_at.isoformat(),
            "run_time_sec": run_time,
        }
        if err_msg:
            ret |= {"status": "failed", "detail": err_msg}
            return ret
        else:
            run_status = state.get(StateKeys.run_status) or ""
            ret |= {"detail": run_status}
            if run_status.lower().startswith("starting"):
                ret |= {"status": "starting"}
            elif run_status:
                ret |= {"status": "running"}
            else:
                ret |= {"status": "completed", "output": state}
            return ret


def _parse_form_data(
    page_cls: typing.Type[BasePage],
    form_data: FormData,
    page_request_json: str,
):
    page_request_data = json.loads(page_request_json)
    # fill in the file urls from the form data
    for key in form_data.keys():
        uf_list = form_data.getlist(key)
        if not (uf_list and isinstance(uf_list[0], UploadFile)):
            continue
        urls = [
            upload_file_from_bytes(uf.filename, uf.file.read(), uf.content_type)
            for uf in uf_list
        ]
        try:
            is_str = (
                page_cls.RequestModel.schema()["properties"][key]["type"] == "string"
            )
        except KeyError:
            raise HTTPException(status_code=400, detail=f'Inavlid file field "{key}"')
        if is_str:
            page_request_data[key] = urls[0]
        else:
            page_request_data.setdefault(key, []).extend(urls)
    # validate the request
    try:
        page_request = page_cls.RequestModel.parse_obj(page_request_data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())
    return page_request


def call_api(
    *,
    page_cls: typing.Type[BasePage],
    user: AppUser,
    request_body: dict,
    query_params,
    run_async: bool = False,
) -> dict:
    created_at = datetime.datetime.utcnow().isoformat()

    self, result, run_id, uid = submit_api_call(
        page_cls=page_cls,
        request_body=request_body,
        user=user,
        query_params=query_params,
    )

    return build_api_response(
        self=self,
        result=result,
        run_id=run_id,
        uid=uid,
        run_async=run_async,
        created_at=created_at,
    )


def submit_api_call(
    *,
    page_cls: typing.Type[BasePage],
    request_body: dict,
    user: AppUser,
    query_params: dict,
) -> tuple[BasePage, "celery.result.AsyncResult", str, str]:
    # init a new page for every request
    self = page_cls(request=SimpleNamespace(user=user))

    # get saved state from db
    state = self.get_doc_from_query_params(query_params).to_dict()
    if state is None:
        raise HTTPException(status_code=404)

    # set sane defaults
    for k, v in self.sane_defaults.items():
        state.setdefault(k, v)

    # remove None values & insert request data
    request_dict = {k: v for k, v in request_body.items() if v is not None}
    state.update(request_dict)

    # set streamlit session state
    st.set_session_state(state)
    st.set_query_params(query_params)

    # check the balance
    if settings.CREDITS_TO_DEDUCT_PER_RUN and not self.check_credits():
        account_url = furl(settings.APP_BASE_URL) / "account"
        raise HTTPException(
            status_code=402,
            detail={
                "error": f"Doh! You need to purchase additional credits to run more Gooey.AI recipes: {account_url}",
            },
        )
    # create a new run
    example_id, run_id, uid = self.create_new_run()
    # submit the task
    result = self.call_runner_task(example_id, run_id, uid)
    return self, result, run_id, uid


def build_api_response(
    *,
    self: BasePage,
    result: "celery.result.AsyncResult",
    run_id: str,
    uid: str,
    run_async: bool,
    created_at: str,
):
    web_url = str(furl(self.app_url(run_id=run_id, uid=uid)))
    if run_async:
        status_url = str(
            furl(settings.API_BASE_URL, query_params=dict(run_id=run_id))
            / self.endpoint.replace("v2", "v3")
            / "status/"
        )
        # return the url to check status
        return {
            "run_id": run_id,
            "web_url": web_url,
            "created_at": created_at,
            "status_url": status_url,
        }
    else:
        # wait for the result
        result.get(disable_sync_subtasks=False)
        state = self.run_doc_sr(run_id, uid).to_dict()
        # check for errors
        err_msg = state.get(StateKeys.error_msg)
        if err_msg:
            raise HTTPException(
                status_code=500,
                detail={
                    "id": run_id,
                    "url": web_url,
                    "created_at": created_at,
                    "error": err_msg,
                },
            )
        else:
            # return updated state
            return {
                "id": run_id,
                "url": web_url,
                "created_at": created_at,
                "output": state,
            }


def setup_pages():
    for page_cls in all_api_pages:
        script_to_api(page_cls)


setup_pages()
