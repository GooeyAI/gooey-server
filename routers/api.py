import datetime
import json
import os
import os.path
import os.path
import typing
from traceback import print_exc
from types import SimpleNamespace

from fastapi import APIRouter
from fastapi import Body
from fastapi import Depends
from fastapi import Form
from fastapi import HTTPException
from furl import furl
from pydantic import BaseModel
from pydantic import ValidationError
from pydantic import create_model
from pydantic.generics import GenericModel
from sentry_sdk import capture_exception
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
)
from daras_ai_v2.base import (
    err_msg_for_exc,
)
from daras_ai_v2.crypto import get_random_doc_id
from gooey_token_authentication1.token_authentication import api_auth_header

app = APIRouter()


class FailedReponseModel(BaseModel):
    id: str | None
    url: str | None
    created_at: str | None
    error: str | None


O = typing.TypeVar("O")


class ApiResponseModel(GenericModel, typing.Generic[O]):
    id: str
    url: str
    created_at: str
    output: O


async def request_form_files(request: Request) -> FormData:
    return await request.form()


def script_to_api(page_cls: typing.Type[BasePage]):
    body_spec = Body(examples=page_cls.RequestModel.Config.schema_extra.get("examples"))

    response_model = create_model(
        page_cls.__name__ + "Response",
        __base__=ApiResponseModel[page_cls.ResponseModel],
    )

    endpoint = page_cls().endpoint

    @app.post(
        os.path.join(endpoint, "form/"),
        response_model=response_model,
        responses={500: {"model": FailedReponseModel}, 402: {}},
        include_in_schema=False,
    )
    @app.post(
        os.path.join(endpoint, "form"),
        response_model=response_model,
        responses={500: {"model": FailedReponseModel}, 402: {}},
        include_in_schema=False,
    )
    def run_api_form(
        request: Request,
        user: AppUser = Depends(api_auth_header),
        form_data=Depends(request_form_files),
        page_request_json: str = Form(alias="json"),
    ):
        page_request_data = json.loads(page_request_json)
        # fill in the file urls from the form data
        form_data: FormData
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
                    page_cls.RequestModel.schema()["properties"][key]["type"]
                    == "string"
                )
            except KeyError:
                raise HTTPException(
                    status_code=400, detail=f'Inavlid file field "{key}"'
                )
            if is_str:
                page_request_data[key] = urls[0]
            else:
                page_request_data.setdefault(key, []).extend(urls)
        # validate the request
        try:
            page_request = page_cls.RequestModel.parse_obj(page_request_data)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=e.errors())
        # call regular json api
        return run_api_json(request, page_request=page_request, user=user)

    @app.post(
        os.path.join(endpoint, ""),
        response_model=response_model,
        responses={500: {"model": FailedReponseModel}, 402: {}},
        operation_id=page_cls.slug_versions[0],
        name=page_cls.title,
    )
    @app.post(
        endpoint,
        response_model=response_model,
        responses={500: {"model": FailedReponseModel}, 402: {}},
        operation_id=page_cls.slug_versions[0],
        include_in_schema=False,
    )
    def run_api_json(
        request: Request,
        user: AppUser = Depends(api_auth_header),
        page_request: page_cls.RequestModel = body_spec,
    ):
        return call_api(
            page_cls=page_cls,
            user=user,
            request_body=page_request.dict(),
            query_params=request.query_params,
        )


def call_api(
    *,
    page_cls: typing.Type[BasePage],
    user: AppUser,
    request_body: dict,
    query_params,
) -> dict:
    created_at = datetime.datetime.utcnow().isoformat()
    # init a new page for every request
    page = page_cls(request=SimpleNamespace(user=user))

    # get saved state from db
    state = page.get_doc_from_query_params(query_params).to_dict()
    if state is None:
        raise HTTPException(status_code=404)

    # set sane defaults
    for k, v in page.sane_defaults.items():
        state.setdefault(k, v)

    # only use the request values, discard outputs
    state = page.RequestModel.parse_obj(state).dict()

    # remove None values & insert request data
    request_dict = {k: v for k, v in request_body.items() if v is not None}
    state.update(request_dict)

    # set streamlit session state
    st.set_session_state(state)
    st.set_query_params(query_params)

    # check the balance
    if user.balance <= 0:
        account_url = furl(settings.APP_BASE_URL) / "account"
        raise HTTPException(
            status_code=402,
            detail={
                "error": f"Doh! You need to purchase additional credits to run more Gooey.AI recipes: {account_url}",
            },
        )

    # create the run
    run_id = get_random_doc_id()
    run_url = str(furl(page.app_url(), query_params=dict(run_id=run_id, uid=user.uid)))
    run_doc_ref = page.run_doc_sr(run_id, user.uid)

    # save the run
    run_doc_ref.set(page.state_to_doc(state))
    # run the script
    try:
        gen = page.run(state)
        try:
            while True:
                next(gen)
        except StopIteration:
            pass
    except Exception as e:
        print_exc()
        capture_exception(e)
        raise HTTPException(
            status_code=500,
            detail={
                "id": run_id,
                "url": run_url,
                "created_at": created_at,
                "error": err_msg_for_exc(e),
            },
        )
    finally:
        # save the run
        run_doc_ref.set(page.state_to_doc(state))

    # deduct credits
    page.deduct_credits(st.session_state)

    # return updated state
    return {
        "id": run_id,
        "url": run_url,
        "created_at": created_at,
        "output": state,
    }


def setup_pages():
    for page_cls in all_api_pages:
        script_to_api(page_cls)


setup_pages()
