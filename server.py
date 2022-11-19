import typing

from fastapi import FastAPI
from fastapi import HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from furl import furl
from google.auth.transport import requests
from google.cloud import firestore
from google.oauth2 import id_token
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

from daras_ai.computer import run_compute_steps
from daras_ai_v2 import settings
from daras_ai_v2.base import BasePage, get_doc_ref, get_saved_doc_nocahe
from pages.ChyronPlant import ChyronPlantPage
from pages.CompareLM import CompareLMPage
from pages.DeforumSD import DeforumSDPage
from pages.EmailFaceInpainting import EmailFaceInpaintingPage
from pages.FaceInpainting import FaceInpaintingPage
from pages.ImageSegmentation import ImageSegmentationPage
from pages.Img2Img import Img2ImgPage
from pages.LetterWriter import LetterWriterPage
from pages.Lipsync import LipsyncPage
from pages.LipsyncTTS import LipsyncTTSPage
from pages.ObjectInpainting import ObjectInpaintingPage
from pages.TextToSpeech import TextToSpeechPage

app = FastAPI(title="GOOEY.AI", docs_url=None, redoc_url="/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")


@app.post("/auth", status_code=302, include_in_schema=False)
async def authentication(request: Request):
    body = await request.body()
    body_str = body.decode("utf-8")
    creds = body_str.split("&")
    token = creds[0].split("=")[1]

    csrf_token_cookie = request.cookies.get("g_csrf_token")
    if not csrf_token_cookie:
        print(400, "No CSRF token in Cookie.")
        RedirectResponse(url="/error", status_code=302)
    csrf_token_body = creds[1].split("=")[1]
    if not csrf_token_body:
        print(400, "No CSRF token in post body.")
        RedirectResponse(url="/error", status_code=302)
    if csrf_token_cookie != csrf_token_body:
        print(400, "Failed to verify double submit cookie.")
        RedirectResponse(url="/error", status_code=302)

    try:
        user = id_token.verify_oauth2_token(
            token,
            requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
        # print(user)
        request.session["user"] = dict(user)

        return RedirectResponse(url="/", status_code=302)

    except ValueError:
        return RedirectResponse(url="/error", status_code=302)


@app.route("/logout", include_in_schema=False)
async def logout(request: Request):
    request.session.pop("user", None)
    return RedirectResponse(url="/")


@app.route("/error", include_in_schema=False)
def error(request: Request):
    return templates.TemplateResponse("error_page.html", context={"request": request})


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
    def run_api(request: page_cls.RequestModel = body_spec):
        # init a new page for every request
        page = page_cls()

        # get saved state from db
        state = get_saved_doc_nocahe(get_doc_ref(page.doc_name))

        # only use the request values, discard outputs
        state = page.RequestModel.parse_obj(state).dict()

        # remove None values & update state
        request_dict = {k: v for k, v in request.dict().items() if v is not None}
        state.update(request_dict)

        # run the script
        try:
            all(page.run(state))
        except Exception as e:
            return JSONResponse(
                status_code=500, content={"error": f"{type(e).__name__} - {e}"}
            )

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
def st_home(request: Request):
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
        state = page.get_doc()
        iframe_url = furl(settings.IFRAME_BASE_URL) / page_cls.slug
        return _st_page(
            request,
            iframe_url,
            context={
                "title": f"{page_cls.title} - Gooey.AI",
                "description": page.preview_description() or "",
                "image": page.preview_image(state) or "",
            },
        )


def _st_page(request: Request, iframe_url: str, *, context: dict):
    f = furl(iframe_url)
    f.query.params["embed"] = "true"
    f.query.params.update(**request.query_params)  # pass down query params

    return templates.TemplateResponse(
        "app.html",
        context={
            "user": request.session.get("user"),
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
]


def setup_pages():
    for page_cls in all_pages:
        script_to_api(page_cls)
        script_to_frontend(page_cls)


setup_pages()
