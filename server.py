import typing

from fastapi import FastAPI
from fastapi import HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from google.auth.transport import requests
from google.cloud import firestore
from google.oauth2 import id_token
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

from daras_ai.computer import run_compute_steps
from daras_ai_v2 import settings
from daras_ai_v2.base import BasePage, get_doc_ref, get_saved_doc_nocahe
from pages.ChyronPlant import ChyronPlantPage
from pages.EmailFaceInpainting import EmailFaceInpaintingPage
from pages.FaceInpainting import FaceInpaintingPage
from pages.ImageSegmentation import ImageSegmentationPage
from pages.LetterWriter import LetterWriterPage
from pages.Lipsync import LipsyncPage

app = FastAPI(title="DarasAI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")

app.add_middleware(SessionMiddleware, secret_key="loveudara")


@app.post("/auth", status_code=302)
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
        print(user)

        request.session["user"] = dict({"email": user["email"], "name": user["name"]})

        return RedirectResponse(url="/", status_code=302)

    except ValueError:
        return RedirectResponse(url="/error", status_code=302)


@app.get("/")
def check(request: Request):
    user = request.session.get("user")
    user_logged_in = False
    if user:
        user_logged_in = True
    return templates.TemplateResponse(
        "index.html", context={"request": request, "user_logged_in": user_logged_in}
    )


@app.route("/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    return RedirectResponse(url="/")


@app.route("/error")
def error(request: Request):
    return templates.TemplateResponse("error_page.html", context={"request": request})


@app.post("/v1/run-recipe/")
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


def script_to_api(page: typing.Type[BasePage]):
    body_spec = Body(examples=page.RequestModel.Config.schema_extra.get("examples"))

    @app.post(page.endpoint, response_model=page.ResponseModel)
    def run_api(request: page.RequestModel = body_spec):
        # get saved state from db
        state = get_saved_doc_nocahe(get_doc_ref(page.doc_name))

        # remove None values & update state
        request_dict = {k: v for k, v in request.dict().items() if v is not None}
        state.update(request_dict)

        # run the script
        all(page().run(state))

        # return updated state
        return state


all_pages = [
    ChyronPlantPage,
    FaceInpaintingPage,
    EmailFaceInpaintingPage,
    LetterWriterPage,
    LipsyncPage,
    ImageSegmentationPage,
]

for page in all_pages:
    script_to_api(page)
