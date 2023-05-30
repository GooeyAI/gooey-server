from gooeysite import wsgi

assert wsgi

import os.path

from app_users.models import AppUser
from daras_ai_v2.copy_to_clipboard_button_widget import copy_to_clipboard_scripts
from daras_ai_v2.meta_content import build_meta_tags
from daras_ai_v2.query_params_util import extract_query_params

import datetime
import json
import re
import typing
from time import time
from traceback import print_exc

from fastapi import FastAPI, Form, Depends
from fastapi import HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from firebase_admin import auth, exceptions
from furl import furl
from pydantic import BaseModel, create_model, ValidationError
from pydantic.generics import GenericModel
from sentry_sdk import capture_exception
from starlette.datastructures import UploadFile, FormData
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import (
    PlainTextResponse,
    Response,
    FileResponse,
)

import gooey_ui as st
from auth_backend import (
    SessionAuthBackend,
    FIREBASE_SESSION_COOKIE,
)
from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2 import settings
from daras_ai_v2.all_pages import all_api_pages
from daras_ai_v2.base import (
    BasePage,
    err_msg_for_exc,
)
from daras_ai_v2.crypto import get_random_doc_id
from daras_ai_v2.settings import templates
from gooey_token_authentication1.token_authentication import api_auth_header
from routers import billing, facebook, talkjs

app = FastAPI(title="GOOEY.AI", docs_url=None, redoc_url="/docs")

app.include_router(billing.router, include_in_schema=False)
app.include_router(talkjs.router, include_in_schema=False)
app.include_router(facebook.router, include_in_schema=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthenticationMiddleware, backend=SessionAuthBackend())
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
app.mount("/static", StaticFiles(directory="static"), name="static")

DEFAULT_LOGIN_REDIRECT = "/explore/"
DEFAULT_LOGOUT_REDIRECT = "/"


@app.middleware("http")
async def logger(request: Request, call_next):
    start_time = time()
    response: Response = await call_next(request)
    response_time = (time() - start_time) * 1000
    print(
        f"{request.method} {request.url} {response.status_code} {response.headers.get('content-length', '-')} - {response_time:.3f} ms"
    )
    return response


@app.get("/sitemap.xml/", include_in_schema=False)
async def get_sitemap():
    my_sitemap = """<?xml version="1.0" encoding="UTF-8"?>
                <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">"""

    all_paths = ["/", "/faq", "/pricing", "/privacy", "/terms"] + [
        page.slug_versions[-1] for page in all_api_pages
    ]

    for path in all_paths:
        url = furl(settings.APP_BASE_URL) / path
        my_sitemap += f"""<url>
              <loc>{url}</loc>
              <lastmod>2022-12-26</lastmod>
              <changefreq>daily</changefreq>
              <priority>1.0</priority>
          </url>"""

    my_sitemap += """</urlset>"""

    return Response(content=my_sitemap, media_type="application/xml")


@app.get("/favicon", include_in_schema=False)
@app.get("/favicon/", include_in_schema=False)
@app.get("/favicon.ico", include_in_schema=False)
@app.get("/favicon.ico/", include_in_schema=False)
async def favicon():
    return FileResponse("static/favicon.ico")


@app.get("/login/", include_in_schema=False)
def login(request: Request):
    if request.user and not request.user.is_anonymous:
        return RedirectResponse(
            request.query_params.get("next", DEFAULT_LOGIN_REDIRECT)
        )
    context = {
        "request": request,
        "settings": settings,
    }
    if request.user and request.user.is_anonymous:
        context["anonymous_user_token"] = auth.create_custom_token(
            request.user.uid
        ).decode()
    return templates.TemplateResponse(
        "login_options.html",
        context=context,
    )


async def form_id_token(request: Request):
    form = await request.form()
    return form.get("idToken", "")


@app.post("/login/", include_in_schema=False)
def authentication(request: Request, id_token: bytes = Depends(form_id_token)):
    ## Taken from https://firebase.google.com/docs/auth/admin/manage-cookies#create_session_cookie

    # To ensure that cookies are set only on recently signed in users, check auth_time in
    # ID token before creating a cookie.
    try:
        decoded_claims = auth.verify_id_token(id_token)
        # Only process if the user signed in within the last 5 minutes.
        if time() - decoded_claims["auth_time"] < 5 * 60:
            expires_in = datetime.timedelta(days=14)
            session_cookie = auth.create_session_cookie(id_token, expires_in=expires_in)
            request.session[FIREBASE_SESSION_COOKIE] = session_cookie
            uid = decoded_claims["uid"]
            # upgrade an anonymous account to a permanent account
            try:
                existing_user = AppUser.objects.get(uid=uid)
                if existing_user.is_anonymous:
                    existing_user.copy_from_firebase_user(auth.get_user(uid))
                    existing_user.save()
            except AppUser.DoesNotExist:
                pass
            return RedirectResponse(
                request.query_params.get("next", DEFAULT_LOGIN_REDIRECT),
                status_code=303,
            )
        # User did not sign in recently. To guard against ID token theft, require
        # re-authentication.
        return PlainTextResponse(status_code=401, content="Recent sign in required")
    except auth.InvalidIdTokenError:
        return PlainTextResponse(status_code=401, content="Invalid ID token")
    except exceptions.FirebaseError:
        return PlainTextResponse(
            status_code=401, content="Failed to create a session cookie"
        )


@app.get("/logout/", include_in_schema=False)
async def logout(request: Request):
    request.session.pop(FIREBASE_SESSION_COOKIE, None)
    return RedirectResponse(request.query_params.get("next", DEFAULT_LOGOUT_REDIRECT))


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


def script_to_api(page_cls: typing.Type[BasePage]):
    body_spec = Body(examples=page_cls.RequestModel.Config.schema_extra.get("examples"))

    response_model = create_model(
        page_cls.__name__ + "Response",
        __base__=ApiResponseModel[page_cls.ResponseModel],
    )

    endpoint = furl(page_cls().endpoint)
    if not endpoint.path.segments[-1]:
        endpoint.path.segments.pop()

    @app.post(
        str(endpoint / "form"),
        response_model=response_model,
        responses={500: {"model": FailedReponseModel}, 402: {}},
        include_in_schema=False,
    )
    @app.post(
        str(endpoint / "form/"),
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
        str(endpoint) + "/",
        response_model=response_model,
        responses={500: {"model": FailedReponseModel}, 402: {}},
        name=page_cls.title,
        operation_id=page_cls.slug_versions[0],
    )
    @app.post(
        str(endpoint),
        response_model=response_model,
        responses={500: {"model": FailedReponseModel}, 402: {}},
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


async def request_form_files(request: Request) -> FormData:
    return await request.form()


def call_api(
    *,
    page_cls: typing.Type[BasePage],
    user: AppUser,
    request_body: dict,
    query_params,
) -> dict:
    created_at = datetime.datetime.utcnow().isoformat()
    # init a new page for every request
    page = page_cls(request=Request(dict(user=user)))

    # get saved state from db
    state = page.get_doc_from_query_params(query_params)
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
    st.session_state = state

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
    run_doc_ref = page.run_doc_ref(run_id, user.uid)

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


async def request_json(request: Request):
    return await request.json()


@app.post("/explore/", include_in_schema=False)
def explore_page(request: Request, json_data: dict = Depends(request_json)):
    import explore

    return st.runner(lambda: page_wrapper(request, explore.render), **json_data)


@app.post("/", include_in_schema=False)
@app.post("/{page_slug}/", include_in_schema=False)
@app.post("/{page_slug}/{tab}/", include_in_schema=False)
def st_page(
    request: Request, page_slug="", tab="", json_data: dict = Depends(request_json)
):
    try:
        page_cls = page_map[normalize_slug(page_slug)]
    except KeyError:
        raise HTTPException(status_code=404)
    # ensure the latest slug is used
    latest_slug = page_cls.slug_versions[-1]
    if latest_slug != page_slug:
        return RedirectResponse(
            request.url.replace(path=os.path.join("/", latest_slug, tab, ""))
        )

    example_id, run_id, uid = extract_query_params(request.query_params)

    page = page_cls(tab=tab, request=request, run_user=get_run_user(request, uid))

    state = json_data.setdefault("state", {})
    if not state:
        state.update(page.get_firestore_state(example_id, run_id, uid))
    if state is None:
        raise HTTPException(status_code=404)

    ret = st.runner(
        lambda: page_wrapper(request, page.render),
        query_params=dict(request.query_params),
        **json_data,
    )
    ret |= {
        "meta": build_meta_tags(
            url=str(request.url),
            page=page,
            state=state,
            run_id=run_id,
            uid=uid,
            example_id=example_id,
        )
        # + [
        #     dict(tagName="link", rel="icon", href="/static/favicon.ico"),
        #     dict(tagName="link", rel="stylesheet", href="/static/css/app.css"),
        # ],
    }
    return ret


def get_run_user(request, uid) -> AppUser | None:
    if not uid:
        return
    if request.user and request.user.uid == uid:
        return request.user
    try:
        return AppUser.objects.get(uid=uid)
    except AppUser.DoesNotExist:
        pass


def page_wrapper(request: Request, render_fn: typing.Callable[[], None]):
    context = {
        "request": request,
        "settings": settings,
        "block_incognito": True,
    }
    if request.user and request.user.is_anonymous:
        context["anonymous_user_token"] = auth.create_custom_token(
            request.user.uid
        ).decode()

    st.html("""<link rel="stylesheet" href="/static/css/app.css">""")
    st.html(templates.get_template("header.html").render(**context))
    st.html(templates.get_template("login_container.html").render(**context))
    st.html(templates.get_template("login_scripts.html").render(**context))
    st.html(copy_to_clipboard_scripts)

    with st.div(id="main-content"):
        render_fn()

    st.html(templates.get_template("footer.html").render(**context))


def normalize_slug(page_slug):
    return re.sub(r"[-_]", "", page_slug.lower())


page_map: dict[str, typing.Type[BasePage]] = {
    normalize_slug(slug): page for page in all_api_pages for slug in page.slug_versions
}


def setup_pages():
    for page_cls in all_api_pages:
        script_to_api(page_cls)


setup_pages()
