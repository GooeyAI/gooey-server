from fastapi import FastAPI, HTTPException, Body
from google.cloud import firestore

from daras_ai.computer import run_compute_steps

app = FastAPI()


@app.post("/v1/run-recipie/")
@app.post("/v1/run-recipe/")
def run(
    params: dict = Body(
        examples={
            "political-ai": {
                "summary": "Political AI example",
                "value": {
                    "recipe_id": "xYlKZM4b5T0",
                    "inputs": {
                        "text_input": {
                            "action_id": "17716",
                        },
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
    for input_step in doc["input_steps"]:
        step_name = input_step["name"]
        match step_name:
            case "text_input":
                var_name = input_step["var_name"]
                try:
                    variables[var_name] = params["inputs"][step_name][var_name]
                except (KeyError, TypeError):
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error": "missing field in request body",
                            "path": ["inputs", step_name, var_name],
                        },
                    )

    compute_steps = doc["compute_steps"]
    run_compute_steps(compute_steps, variables)

    outputs = {}

    for output_step in doc["output_steps"]:
        match output_step["name"]:
            case "raw_text_output":
                var_name = output_step["var_name"]
                outputs[var_name] = variables[var_name]

    return {"outputs": outputs}
