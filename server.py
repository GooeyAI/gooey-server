import datetime
import re
import time
import typing

import httpx
import streamlit
from fastapi import FastAPI, Depends
from fastapi import HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from firebase_admin import auth, exceptions
from furl import furl
from google.cloud import firestore
from lxml.html import HtmlElement
from pydantic import BaseModel, create_model
from pyquery import PyQuery as pq
from sentry_sdk import capture_exception
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response, FileResponse

from auth_backend import (
    SessionAuthBackend,
    FIREBASE_SESSION_COOKIE,
)
from daras_ai.computer import run_compute_steps
from daras_ai_v2 import settings, db
from daras_ai_v2.base import (
    BasePage,
    err_msg_for_exc,
    ApiResponseModel,
    DEFAULT_META_IMG,
)
from daras_ai_v2.crypto import get_random_doc_id
from daras_ai_v2.meta_content import meta_title_for_page, meta_description_for_page
from gooey_token_authentication1.token_authentication import api_auth_header
from recipes.ChyronPlant import ChyronPlantPage
from recipes.CompareText2Img import CompareText2ImgPage
from recipes.DeforumSD import DeforumSDPage
from recipes.EmailFaceInpainting import EmailFaceInpaintingPage
from recipes.FaceInpainting import FaceInpaintingPage
from recipes.GoogleImageGen import GoogleImageGenPage
from recipes.ImageSegmentation import ImageSegmentationPage
from recipes.Img2Img import Img2ImgPage
from recipes.LetterWriter import LetterWriterPage
from recipes.Lipsync import LipsyncPage
from recipes.LipsyncTTS import LipsyncTTSPage
from recipes.ObjectInpainting import ObjectInpaintingPage
from recipes.SEOSummary import SEOSummaryPage
from recipes.SocialLookupEmail import SocialLookupEmailPage
from recipes.TextToSpeech import TextToSpeechPage
from recipes.VideoBots import VideoBotsPage
from routers import billing

app = FastAPI(title="GOOEY.AI", docs_url=None, redoc_url="/docs")

app.include_router(billing.router)
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

templates = Jinja2Templates(directory="templates")


@app.get("/sitemap.xml/", include_in_schema=False)
async def get_sitemap():
    my_sitemap = """<?xml version="1.0" encoding="UTF-8"?>
                <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">"""

    all_paths = ["/", "/faq", "/pricing", "/privacy", "/terms"] + [
        page.slug_versions[-1] for page in all_pages
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


@app.get("/favicon.ico/", include_in_schema=False)
async def favicon():
    return FileResponse("static/favicon.ico")


_proxy_client = httpx.AsyncClient(base_url=settings.WIX_SITE_URL)


@app.exception_handler(404)
async def custom_404_handler(request: Request, exc):
    url = httpx.URL(path=request.url.path, query=request.url.query.encode("utf-8"))
    req = _proxy_client.build_request(
        request.method,
        url,
        headers={"user-agent": request.headers.get("user-agent", "")},
    )
    resp = await _proxy_client.send(req)

    if resp.status_code == 404:
        return templates.TemplateResponse(
            "404.html",
            {"request": request},
            status_code=404,
        )
    elif resp.status_code != 200 or "text/html" not in resp.headers["content-type"]:
        return Response(content=resp.content, status_code=resp.status_code)

    # convert links
    d = pq(resp.content)
    for el in d("a"):
        el: HtmlElement
        href = el.attrib["href"]
        if href == "https://app.gooey.ai":
            href = "/explore/"
        elif href.startswith(settings.WIX_SITE_URL):
            href = href[len(settings.WIX_SITE_URL) :]
            if not href.startswith("/"):
                href = "/" + href
        else:
            continue
        el.attrib["href"] = href

    return templates.TemplateResponse(
        "wix_site.html",
        context={
            "request": request,
            "wix_site_html": d.outer_html(),
        },
    )


@app.get("/login", include_in_schema=False)
def authentication(request: Request):
    if request.user:
        return RedirectResponse(url=request.query_params.get("next", "/"))
    return templates.TemplateResponse(
        "login_options.html",
        context={
            "request": request,
        },
    )


@app.post("/sessionLogin", include_in_schema=False)
async def authentication(request: Request):
    ## Taken from https://firebase.google.com/docs/auth/admin/manage-cookies#create_session_cookie

    # Get the ID token sent by the client
    id_token = await request.body()

    # To ensure that cookies are set only on recently signed in users, check auth_time in
    # ID token before creating a cookie.
    try:
        decoded_claims = auth.verify_id_token(id_token)
        # Only process if the user signed in within the last 5 minutes.
        if time.time() - decoded_claims["auth_time"] < 5 * 60:
            expires_in = datetime.timedelta(days=14)
            session_cookie = auth.create_session_cookie(id_token, expires_in=expires_in)
            request.session[FIREBASE_SESSION_COOKIE] = session_cookie
            return JSONResponse(content={"status": "success"})
        # User did not sign in recently. To guard against ID token theft, require
        # re-authentication.
        return PlainTextResponse(status_code=401, content="Recent sign in required")
    except auth.InvalidIdTokenError:
        return PlainTextResponse(status_code=401, content="Invalid ID token")
    except exceptions.FirebaseError:
        return PlainTextResponse(
            status_code=401, content="Failed to create a session cookie"
        )


@app.get("/logout", include_in_schema=False)
async def logout(request: Request):
    request.session.pop(FIREBASE_SESSION_COOKIE, None)
    return RedirectResponse(url=request.query_params.get("next", "/"))


@app.post("/v1/run-recipe/", include_in_schema=False)
def run(
    params: dict = Body(
        examples={
            "political-ai": {
                "summary": "Political AI example",
                "value": {
                    "recipe_id": "xYlKZM4b5T0",
                    "inputs": {
                        "action_id": "17716",
                    },
                },
            },
        },
    ),
):
    recipe_id = params.get("recipie_id", params.get("recipe_id", None))
    if not recipe_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "missing field in request body",
                "path": ["recipe_id"],
            },
        )

    db = firestore.Client()
    db_collection = db.collection("daras-ai--political_example")
    doc_ref = db_collection.document(recipe_id)
    doc = doc_ref.get().to_dict()

    variables = {}

    # put input steps parameters into variables
    for input_step in doc["input_steps"]:
        var_name = input_step["var_name"]
        try:
            variables[var_name] = params["inputs"][var_name]
        except (KeyError, TypeError):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "missing field in request body",
                    "path": ["inputs", var_name],
                },
            )

    # run compute steps
    compute_steps = doc["compute_steps"]
    run_compute_steps(compute_steps, variables)

    # put output steps parameters into variables
    outputs = {}
    for output_step in doc["output_steps"]:
        var_name = output_step["var_name"]
        outputs[var_name] = variables[var_name]

    return {"outputs": outputs}


class FailedReponseModel(BaseModel):
    id: str | None
    url: str | None
    created_at: str | None
    error: str | None


def script_to_api(page_cls: typing.Type[BasePage]):
    body_spec = Body(examples=page_cls.RequestModel.Config.schema_extra.get("examples"))

    response_model = create_model(
        page_cls.__name__ + "Response",
        __base__=ApiResponseModel[page_cls.ResponseModel],
    )

    @app.post(
        page_cls().endpoint,
        response_model=response_model,
        responses={500: {"model": FailedReponseModel}, 402: {}},
        name=page_cls.title,
        operation_id=page_cls.slug_versions[0],
    )
    def run_api(
        request: Request,
        user: auth.UserRecord = Depends(api_auth_header),
        page_request: page_cls.RequestModel = body_spec,
    ):
        # init a new page for every request
        page = page_cls()

        # check the balance
        balance = db.get_doc_field(
            db.get_user_doc_ref(user.uid), db.USER_BALANCE_FIELD, 0
        )
        if balance < page.get_price():
            account_url = furl(settings.APP_BASE_URL) / "account"
            return JSONResponse(
                status_code=402,
                content={
                    "error": f"Doh! You need to purchase additional credits to run more Gooey.AI recipes: {account_url}",
                },
            )

        created_at = datetime.datetime.utcnow().isoformat()

        # get saved state from db
        state = page.get_doc_from_query_params(request.query_params)
        if state is None:
            raise HTTPException(status_code=404)

        # set sane defaults
        for k, v in page.sane_defaults.items():
            state.setdefault(k, v)

        # only use the request values, discard outputs
        state = page.RequestModel.parse_obj(state).dict()

        # remove None values & update state
        request_dict = {k: v for k, v in page_request.dict().items() if v is not None}
        state.update(request_dict)

        # set the current user
        state["_current_user"] = user
        streamlit.session_state = state

        # create the run
        run_id = get_random_doc_id()
        run_url = str(
            furl(page.app_url(), query_params=dict(run_id=run_id, uid=user.uid))
        )
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
            capture_exception(e)
            return JSONResponse(
                status_code=500,
                content={
                    "id": run_id,
                    "url": run_url,
                    "created_at": created_at,
                    "error": err_msg_for_exc(e),
                },
            )

        # save the run
        run_doc_ref.set(page.state_to_doc(state))
        # deuct credits
        page.deduct_credits()

        # return updated state
        return {
            "id": run_id,
            "url": run_url,
            "created_at": created_at,
            "output": state,
        }


@app.get("/explore/", include_in_schema=False)
def st_home(request: Request):
    iframe_url = furl(settings.IFRAME_BASE_URL).url
    return _st_page(
        request,
        iframe_url,
        context={
            "title": "Explore - Gooey.AI",
            "image": DEFAULT_META_IMG,
        },
    )


@app.get("/Editor/", include_in_schema=False)
def st_editor(request: Request):
    iframe_url = furl(settings.IFRAME_BASE_URL) / "Editor"
    return _st_page(
        request,
        iframe_url,
        block_incognito=True,
        context={"title": f"Gooey.AI"},
    )


@app.get("/{page_slug}/", include_in_schema=False)
def st_page(request: Request, page_slug):
    page_slug = normalize_slug(page_slug)
    try:
        page_cls = page_map[page_slug]
    except KeyError:
        raise HTTPException(status_code=404)
    page = page_cls()

    state = page.get_doc_from_query_params(dict(request.query_params))
    if state is None:
        raise HTTPException(status_code=404)

    iframe_url = furl(
        settings.IFRAME_BASE_URL, query_params={"page_slug": page_cls.slug_versions[0]}
    )
    example_id, run_id, uid = page.extract_query_params(dict(request.query_params))

    return _st_page(
        request,
        str(iframe_url),
        block_incognito=True,
        context={
            "title": meta_title_for_page(
                page=page,
                state=state,
                run_id=run_id,
                uid=uid,
                example_id=example_id,
            ),
            "description": meta_description_for_page(
                page=page,
                state=state,
                run_id=run_id,
                uid=uid,
                example_id=example_id,
            ),
            "image": page.preview_image(state),
        },
    )


def _st_page(
    request: Request,
    iframe_url: str,
    *,
    block_incognito: bool = False,
    context: dict,
):
    f = furl(iframe_url)
    f.query.params["embed"] = "true"
    f.query.params.update(**request.query_params)  # pass down query params

    db.get_or_init_user_data(request)

    return templates.TemplateResponse(
        "st_page.html",
        context={
            "request": request,
            "iframe_url": f.url,
            "settings": settings,
            "block_incognito": block_incognito,
            **context,
        },
    )


all_pages: list[typing.Type[BasePage]] = [
    ChyronPlantPage,
    FaceInpaintingPage,
    EmailFaceInpaintingPage,
    LetterWriterPage,
    LipsyncPage,
    # CompareLMPage,
    ImageSegmentationPage,
    TextToSpeechPage,
    LipsyncTTSPage,
    DeforumSDPage,
    Img2ImgPage,
    ObjectInpaintingPage,
    SocialLookupEmailPage,
    CompareText2ImgPage,
    SEOSummaryPage,
    GoogleImageGenPage,
    VideoBotsPage,
]


def normalize_slug(page_slug):
    return re.sub(r"[-_]", "", page_slug.lower())


page_map: dict[str, typing.Type[BasePage]] = {
    normalize_slug(slug): page for page in all_pages for slug in page.slug_versions
}


def setup_pages():
    for page_cls in all_pages:
        script_to_api(page_cls)


setup_pages()
