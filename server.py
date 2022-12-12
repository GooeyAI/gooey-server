import datetime
import time
import typing

import requests
from fastapi import FastAPI
from fastapi import FastAPI, Header
from fastapi import HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from firebase_admin import auth, exceptions
from furl import furl
from google.cloud import firestore
from pydantic import BaseModel
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from auth_backend import (
    SessionAuthBackend,
    FIREBASE_SESSION_COOKIE,
    ANONYMOUS_USER_COOKIE,
)
from daras_ai.computer import run_compute_steps
from daras_ai_v2 import settings
from gooey_token_authentication1.token_authentication import authenticate
from pages.GoogleImageGen import GoogleImageGenPage
from daras_ai_v2.base import (
    BasePage,
    get_doc_ref,
    get_or_create_doc,
    err_msg_for_exc,
)
from pages.ChyronPlant import ChyronPlantPage
from pages.CompareLM import CompareLMPage
from pages.CompareText2Img import CompareText2ImgPage
from pages.DeforumSD import DeforumSDPage
from pages.EmailFaceInpainting import EmailFaceInpaintingPage
from pages.FaceInpainting import FaceInpaintingPage
from pages.ImageSegmentation import ImageSegmentationPage
from pages.Img2Img import Img2ImgPage
from pages.LetterWriter import LetterWriterPage
from pages.Lipsync import LipsyncPage
from pages.LipsyncTTS import LipsyncTTSPage
from pages.ObjectInpainting import ObjectInpaintingPage
from pages.SEOSummary import SEOSummaryPage
from pages.SocialLookupEmail import SocialLookupEmailPage
from pages.TextToSpeech import TextToSpeechPage

app = FastAPI(title="GOOEY.AI", docs_url=None, redoc_url="/docs")

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


@app.exception_handler(404)
async def custom_404_handler(request: Request, exc):
    return templates.TemplateResponse("404.html", {"request": request})


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


class RunFailedModel(BaseModel):
    error: str


def script_to_api(page_cls: typing.Type[BasePage]):
    body_spec = Body(examples=page_cls.RequestModel.Config.schema_extra.get("examples"))

    @app.post(
        page_cls().endpoint,
        response_model=page_cls.ResponseModel,
        responses={500: {"model": RunFailedModel}},
        name=page_cls.title,
    )
    def run_api(
        request: Request,
        Authorization: typing.Union[str, None] = Header(
            default=None, description="Token $GOOEY_API_TOKEN"
        ),
        page_request: page_cls.RequestModel = body_spec,
    ):
        # Authenticate Token
        authenticate(Authorization)

        # init a new page for every request
        page = page_cls()

        # get saved state from db
        state = get_or_create_doc(get_doc_ref(page.doc_name)).to_dict()

        # set sane defaults
        for k, v in page.sane_defaults.items():
            state.setdefault(k, v)

        # only use the request values, discard outputs
        state = page.RequestModel.parse_obj(state).dict()

        # remove None values & update state
        request_dict = {k: v for k, v in page_request.dict().items() if v is not None}
        state.update(request_dict)

        # pass current user from request
        state["_current_user"] = request.user

        # run the script
        try:
            gen = page.run(state)
            try:
                while True:
                    next(gen)
            except StopIteration:
                pass
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": err_msg_for_exc(e)})

        # return updated state
        return state


@app.get("/", include_in_schema=False)
def st_home(request: Request):
    iframe_url = furl(settings.IFRAME_BASE_URL).url
    return _st_page(
        request,
        iframe_url,
        context={"title": "Home - Gooey.AI"},
    )


@app.get("/Editor/", include_in_schema=False)
def st_editor(request: Request):
    iframe_url = furl(settings.IFRAME_BASE_URL) / "Editor"
    return _st_page(
        request,
        iframe_url,
        context={"title": f"Gooey.AI"},
    )


def script_to_frontend(page_cls: typing.Type[BasePage]):
    @app.get(f"/{page_cls.slug}/", include_in_schema=False)
    def st_page(request: Request):
        page = page_cls()
        state = page.get_doc_from_query_params(dict(request.query_params))
        if state is None:
            raise HTTPException(status_code=404)
        iframe_url = furl(settings.IFRAME_BASE_URL) / page_cls.slug
        return _st_page(
            request,
            iframe_url,
            context={
                "title": f"{page_cls.title} - Gooey.AI",
                "description": page.preview_description(state),
                "image": page.preview_image(state),
            },
        )


def _st_page(request: Request, iframe_url: str, *, context: dict):
    f = furl(iframe_url)
    f.query.params["embed"] = "true"
    f.query.params.update(**request.query_params)  # pass down query params

    if not (request.user or request.session.get(ANONYMOUS_USER_COOKIE)):
        request.session[ANONYMOUS_USER_COOKIE] = {
            "uid": auth.create_user().uid,
        }

    return templates.TemplateResponse(
        "app.html",
        context={
            "request": request,
            "iframe_url": f.url,
            "settings": settings,
            **context,
        },
    )


all_pages = [
    ChyronPlantPage,
    FaceInpaintingPage,
    EmailFaceInpaintingPage,
    LetterWriterPage,
    LipsyncPage,
    CompareLMPage,
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
]


def setup_pages():
    for page_cls in all_pages:
        script_to_api(page_cls)
        script_to_frontend(page_cls)


setup_pages()
