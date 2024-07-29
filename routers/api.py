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
from fastapi.exceptions import RequestValidationError
from furl import furl
from pydantic import BaseModel, Field
from pydantic import ValidationError
from pydantic import create_model
from pydantic.error_wrappers import ErrorWrapper
from pydantic.generics import GenericModel
from starlette.datastructures import FormData
from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.status import (
    HTTP_402_PAYMENT_REQUIRED,
    HTTP_429_TOO_MANY_REQUESTS,
    HTTP_500_INTERNAL_SERVER_ERROR,
    HTTP_400_BAD_REQUEST,
)

import gooey_gui as gui
from app_users.models import AppUser
from auth.token_authentication import api_auth_header
from bots.models import RetentionPolicy
from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2 import settings
from daras_ai_v2.all_pages import all_api_pages
from daras_ai_v2.base import (
    BasePage,
    RecipeRunState,
)
from daras_ai_v2.fastapi_tricks import fastapi_request_form
from functions.models import CalledFunctionResponse
from gooeysite.bg_db_conn import get_celery_result_db_safe

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


class GenericErrorResponseDetail(BaseModel):
    error: str


class GenericErrorResponse(BaseModel):
    detail: GenericErrorResponseDetail


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
    run_time_sec: float = Field(description="Total run time in seconds")
    status: RecipeRunState = Field(description="Status of the run")
    detail: str = Field(
        description="Details about the status of the run as a human readable string"
    )
    output: O | None = Field(
        description='Output of the run. Only available if status is `"completed"`'
    )


class RunSettings(BaseModel):
    retention_policy: typing.Literal[tuple(RetentionPolicy.names)] = Field(
        default=RetentionPolicy.keep.name,
        description="Policy for retaining the run data.",
    )


def script_to_api(page_cls: typing.Type[BasePage]):
    endpoint = page_cls().endpoint.rstrip("/")
    # add the common settings to the request model
    request_model = create_model(
        page_cls.__name__ + "Request",
        __base__=page_cls.RequestModel,
        settings=(RunSettings, RunSettings()),
    )
    # encapsulate the response model with the ApiResponseModel
    response_output_model = create_model(
        page_cls.__name__ + "Output",
        __base__=page_cls.ResponseModel,
        called_functions=(list[CalledFunctionResponse], None),
    )
    response_model = create_model(
        page_cls.__name__ + "Response",
        __base__=ApiResponseModelV2[response_output_model],
    )

    common_errs = {
        HTTP_402_PAYMENT_REQUIRED: {"model": GenericErrorResponse},
        HTTP_429_TOO_MANY_REQUESTS: {"model": GenericErrorResponse},
    }

    @app.post(
        os.path.join(endpoint, ""),
        response_model=response_model,
        responses={
            HTTP_500_INTERNAL_SERVER_ERROR: {"model": FailedReponseModelV2},
            **common_errs,
        },
        operation_id=page_cls.slug_versions[0],
        tags=[page_cls.title],
        name=page_cls.title + " (v2 sync)",
    )
    @app.post(
        endpoint,
        response_model=response_model,
        responses={
            HTTP_500_INTERNAL_SERVER_ERROR: {"model": FailedReponseModelV2},
            **common_errs,
        },
        include_in_schema=False,
    )
    def run_api_json(
        request: Request,
        page_request: request_model,
        user: AppUser = Depends(api_auth_header),
    ):
        return _run_api(
            page_cls=page_cls,
            user=user,
            request_body=page_request.dict(exclude_unset=True),
            query_params=dict(request.query_params),
            run_settings=page_request.settings,
        )

    @app.post(
        os.path.join(endpoint, "form/"),
        response_model=response_model,
        responses={
            HTTP_500_INTERNAL_SERVER_ERROR: {"model": FailedReponseModelV2},
            HTTP_400_BAD_REQUEST: {"model": GenericErrorResponse},
            **common_errs,
        },
        include_in_schema=False,
    )
    @app.post(
        os.path.join(endpoint, "form"),
        response_model=response_model,
        responses={
            HTTP_500_INTERNAL_SERVER_ERROR: {"model": FailedReponseModelV2},
            HTTP_400_BAD_REQUEST: {"model": GenericErrorResponse},
            **common_errs,
        },
        include_in_schema=False,
    )
    def run_api_form(
        request: Request,
        user: AppUser = Depends(api_auth_header),
        form_data=fastapi_request_form,
        page_request_json: str = Form(alias="json"),
    ):
        # parse form data
        page_request = _parse_form_data(request_model, form_data, page_request_json)
        # call regular json api
        return run_api_json(request, page_request=page_request, user=user)

    endpoint = endpoint.replace("v2", "v3")
    response_model = AsyncApiResponseModelV3

    @app.post(
        os.path.join(endpoint, "async/"),
        response_model=response_model,
        responses=common_errs,
        operation_id="async__" + page_cls.slug_versions[0],
        name=page_cls.title + " (v3 async)",
        tags=[page_cls.title],
        status_code=202,
    )
    @app.post(
        os.path.join(endpoint, "async"),
        response_model=response_model,
        responses=common_errs,
        include_in_schema=False,
        status_code=202,
    )
    def run_api_json_async(
        request: Request,
        response: Response,
        page_request: request_model,
        user: AppUser = Depends(api_auth_header),
    ):
        ret = _run_api(
            page_cls=page_cls,
            user=user,
            request_body=page_request.dict(exclude_unset=True),
            query_params=dict(request.query_params),
            run_async=True,
            run_settings=page_request.settings,
        )
        response.headers["Location"] = ret["status_url"]
        response.headers["Access-Control-Expose-Headers"] = "Location"
        return ret

    @app.post(
        os.path.join(endpoint, "async/form/"),
        response_model=response_model,
        responses={
            HTTP_400_BAD_REQUEST: {"model": GenericErrorResponse},
            **common_errs,
        },
        include_in_schema=False,
    )
    @app.post(
        os.path.join(endpoint, "async/form"),
        response_model=response_model,
        responses={
            HTTP_400_BAD_REQUEST: {"model": GenericErrorResponse},
            **common_errs,
        },
        include_in_schema=False,
    )
    def run_api_form_async(
        request: Request,
        response: Response,
        user: AppUser = Depends(api_auth_header),
        form_data=fastapi_request_form,
        page_request_json: str = Form(alias="json"),
    ):
        # parse form data
        page_request = _parse_form_data(request_model, form_data, page_request_json)
        # call regular json api
        return run_api_json_async(
            request, response=response, page_request=page_request, user=user
        )

    response_model = create_model(
        page_cls.__name__ + "StatusResponse",
        __base__=AsyncStatusResponseModelV3[response_output_model],
    )

    @app.get(
        os.path.join(endpoint, "status/"),
        response_model=response_model,
        responses=common_errs,
        operation_id="status__" + page_cls.slug_versions[0],
        tags=[page_cls.title],
        name=page_cls.title + " (v3 status)",
    )
    @app.get(
        os.path.join(endpoint, "status"),
        response_model=response_model,
        responses=common_errs,
        include_in_schema=False,
    )
    def get_run_status(
        run_id: str,
        user: AppUser = Depends(api_auth_header),
    ):
        self = page_cls()
        sr = self.get_sr_from_query_params(example_id=None, run_id=run_id, uid=user.uid)
        web_url = str(furl(self.app_url(run_id=run_id, uid=user.uid)))
        ret = {
            "run_id": run_id,
            "web_url": web_url,
            "created_at": sr.created_at.isoformat(),
            "run_time_sec": sr.run_time.total_seconds(),
        }
        if sr.error_code:
            raise HTTPException(sr.error_code, detail=ret | {"error": sr.error_msg})
        elif sr.error_msg:
            ret |= {"status": "failed", "detail": sr.error_msg}
        else:
            status = self.get_run_state(sr.to_dict())
            ret |= {"detail": sr.run_status or "", "status": status}
            if status == RecipeRunState.completed and sr.state:
                ret |= {"output": sr.api_output()}
                if sr.retention_policy == RetentionPolicy.delete:
                    sr.state = {}
                    sr.save(update_fields=["state"])
            return ret


def _parse_form_data(
    request_model: typing.Type[BaseModel],
    form_data: FormData,
    page_request_json: str,
):
    # load the json data
    try:
        page_request_data = json.loads(page_request_json)
    except json.JSONDecodeError as e:
        raise RequestValidationError(
            [ErrorWrapper(e, ("body", e.pos))], body=e.doc
        ) from e
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
            is_str = request_model.schema()["properties"][key]["type"] == "string"
        except KeyError:
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=dict(error=f'Inavlid file field "{key}"'),
            )
        if is_str:
            page_request_data[key] = urls[0]
        else:
            page_request_data.setdefault(key, []).extend(urls)
    # validate the request
    try:
        page_request = request_model.parse_obj(page_request_data)
    except ValidationError as e:
        raise RequestValidationError(e.raw_errors, body=page_request_data) from e
    return page_request


def _run_api(
    *,
    page_cls: typing.Type[BasePage],
    user: AppUser,
    request_body: dict,
    query_params,
    run_async: bool = False,
    run_settings: RunSettings,
) -> dict:
    page, result, run_id, uid = submit_api_call(
        page_cls=page_cls,
        request_body=request_body,
        user=user,
        query_params=query_params,
        retention_policy=RetentionPolicy[run_settings.retention_policy],
        enable_rate_limits=True,
    )
    response = build_api_response(
        page=page,
        result=result,
        run_id=run_id,
        uid=uid,
        run_async=run_async,
    )
    return response


def submit_api_call(
    *,
    page_cls: typing.Type[BasePage],
    request_body: dict,
    user: AppUser,
    query_params: dict,
    retention_policy: RetentionPolicy = None,
    enable_rate_limits: bool = False,
) -> tuple[BasePage, "celery.result.AsyncResult", str, str]:
    # init a new page for every request
    self = page_cls(request=SimpleNamespace(user=user))

    # get saved state from db
    query_params.setdefault("uid", user.uid)
    sr = self.get_sr_from_query_params_dict(query_params)
    state = self.load_state_from_sr(sr)
    # load request data
    state.update(request_body)

    # set streamlit session state
    gui.set_session_state(state)
    gui.set_query_params(query_params)

    # create a new run
    try:
        sr = self.create_new_run(
            enable_rate_limits=enable_rate_limits,
            is_api_call=True,
            retention_policy=retention_policy or RetentionPolicy.keep,
        )
    except ValidationError as e:
        raise RequestValidationError(e.raw_errors, body=gui.session_state) from e
    # submit the task
    result = self.call_runner_task(sr)
    return self, result, sr.run_id, sr.uid


def build_api_response(
    *,
    page: BasePage,
    result: "celery.result.AsyncResult",
    run_id: str,
    uid: str,
    run_async: bool,
):
    web_url = page.app_url(run_id=run_id, uid=uid)
    if run_async:
        status_url = str(
            furl(settings.API_BASE_URL, query_params=dict(run_id=run_id))
            / page.endpoint.replace("v2", "v3")
            / "status/"
        )
        sr = page.run_doc_sr(run_id, uid)
        # return the url to check status
        return {
            "run_id": run_id,
            "web_url": web_url,
            "created_at": sr.created_at.isoformat(),
            "status_url": status_url,
        }
    else:
        # wait for the result
        get_celery_result_db_safe(result)
        sr = page.run_doc_sr(run_id, uid)
        if sr.retention_policy == RetentionPolicy.delete:
            sr.state = {}
            sr.save(update_fields=["state"])
        # check for errors
        if sr.error_msg:
            raise HTTPException(
                status_code=sr.error_code or HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "id": run_id,
                    "url": web_url,
                    "created_at": sr.created_at.isoformat(),
                    "error": sr.error_msg,
                },
            )
        else:
            # return updated state
            return {
                "id": run_id,
                "url": web_url,
                "created_at": sr.created_at.isoformat(),
                "output": sr.api_output(),
            }


def setup_pages():
    for page_cls in all_api_pages:
        script_to_api(page_cls)


setup_pages()


class BalanceResponse(BaseModel):
    balance: int = Field(description="Current balance in credits")


@app.get("/v1/balance/", response_model=BalanceResponse, tags=["Misc"])
def get_balance(user: AppUser = Depends(api_auth_header)):
    return BalanceResponse(balance=user.balance)
