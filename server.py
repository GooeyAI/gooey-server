from fastapi import FastAPI, HTTPException, Body
from google.cloud import firestore

from daras_ai.computer import run_compute_steps
from pages import ChyronPlant, FaceInpainting, EmailFaceInpainting

app = FastAPI(
    title="DarasAI",
)


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


@app.post(ChyronPlant.API_URL, response_model=ChyronPlant.ResponseModel)
def run_api(params: ChyronPlant.RequestModel):
    state = ChyronPlant.get_saved_state(ChyronPlant.DOC_NAME)

    # remove None values
    params_dict = {k: v for k, v in params.dict().items() if v is not None}
    state.update(params_dict)

    # run the script
    all(ChyronPlant.run(state))

    return state


def script_to_api(module):
    @app.post(module.API_URL, response_model=module.ResponseModel)
    def run_api(params: module.RequestModel):
        state = module.get_saved_state(module.DOC_NAME)

        # remove None values
        params_dict = {k: v for k, v in params.dict().items() if v is not None}
        state.update(params_dict)

        # run the script
        all(module.run(state))

        return state


script_to_api(ChyronPlant)
script_to_api(FaceInpainting)
script_to_api(EmailFaceInpainting)
