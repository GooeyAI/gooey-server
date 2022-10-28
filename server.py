import typing

from fastapi import FastAPI, HTTPException, Body
from google.cloud import firestore

from daras_ai.computer import run_compute_steps
from daras_ai_v2.base import DarsAiPage, get_saved_doc, get_doc_ref
from pages.ChyronPlant import ChyronPlantPage
from pages.EmailFaceInpainting import EmailFaceInpaintingPage
from pages.FaceInpainting import FaceInpaintingPage
from pages.LetterWriter import LetterWriterPage
from pages.Lipsync import LipsyncPage

app = FastAPI(title="DarasAI")


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


def script_to_api(page: typing.Type[DarsAiPage]):
    body_spec = Body(examples=page.RequestModel.Config.schema_extra.get("examples"))

    @app.post(page.endpoint, response_model=page.ResponseModel)
    def run_api(request: page.RequestModel = body_spec):
        # get saved state from db
        state = get_saved_doc(get_doc_ref(page.doc_name))

        # remove None values & update state
        request_dict = {k: v for k, v in request.dict().items() if v is not None}
        state.update(request_dict)

        # run the script
        all(page().run(state))

        # return updated state
        return state


script_to_api(ChyronPlantPage)
script_to_api(FaceInpaintingPage)
script_to_api(EmailFaceInpaintingPage)
script_to_api(LetterWriterPage)
script_to_api(LipsyncPage)
