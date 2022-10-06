import ast
import json
import random

import openai
import parse
from decouple import config
from fastapi import FastAPI, HTTPException, Body
from glom import glom
from google.cloud import firestore

from daras_ai.train_data_formatter import input_spec_parse_pattern


app = FastAPI()


@app.post("/api/v1/run-recipie/")
def run(
    params: dict = Body(
        examples={
            "political-ai": {
                "summary": "Political AI example",
                "value": {
                    "recipie_id": "xYlKZM4b5T0",
                    "inputs": {"text_input": {"action_id": "17477"}},
                },
            }
        }
    )
):
    db = firestore.Client()
    db_collection = db.collection("daras-ai--political_example")
    try:
        recipie_id = params["recipie_id"]
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "missing field in request body",
                "path": ["recipie_id"],
            },
        )
    doc_ref = db_collection.document(recipie_id)
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

    for compute_step in doc["compute_steps"]:
        match compute_step["name"]:
            case "text_train_data":
                variables[compute_step["out_var"]] = json.loads(
                    compute_step["training_data"]
                )
            case "language_model_prompt_gen":
                prompt_header = compute_step["prompt_header"]
                completion_prefix = compute_step["completion_prefix"]
                training_data_var = compute_step["Training data input var"]
                num_prompts = compute_step["num_prompts"]
                prompt_sep = compute_step["prompt_sep"]
                completion_sep = compute_step["completion_sep"]
                final_prompt_var = compute_step["Final prompt out var"]
                prompt_input_var = compute_step["prompt_input_var"]

                prompt_input = prompt_input_var
                input_spec_results: list[parse.Result] = list(
                    parse.findall(input_spec_parse_pattern, prompt_input)
                )
                for spec_result in input_spec_results:
                    spec = spec_result.fixed[0]
                    variable_value = glom(variables, ast.literal_eval(spec))
                    prompt_input = prompt_input.replace(
                        "{{" + spec + "}}", variable_value
                    )

                completion_prefix = completion_prefix.strip() + " "
                final_prompt = prompt_header.strip() + "\n\n"
                for eg in random.choices(variables[training_data_var], k=num_prompts):
                    final_prompt += (
                        eg["prompt"]
                        + prompt_sep
                        + completion_prefix
                        + eg["completion"]
                        + completion_sep
                    )

                final_prompt += prompt_input + prompt_sep + completion_prefix
                variables[final_prompt_var] = final_prompt
            case "language_model":
                api_provider = compute_step["api_provider#1"]
                selected_engine = compute_step["selected_engine#1"]
                max_tokens = compute_step["max_tokens"]
                final_prompt_var = compute_step["Final prompt input var"]
                stop = json.loads(compute_step["stop"])
                num_outputs = compute_step["num_outputs"]
                num_candidates = compute_step["num_candidates"]
                output_var = compute_step["Model output var"]

                match api_provider:
                    case "openai":
                        openai.api_key = config("OPENAI_API_KEY")
                        openai.api_base = "https://api.openai.com/v1"
                    case "goose.ai":
                        openai.api_key = config("GOOSEAI_API_KEY")
                        openai.api_base = "https://api.goose.ai/v1"
                    case _:
                        raise ValueError()

                r = openai.Completion.create(
                    engine=selected_engine,
                    max_tokens=max_tokens,
                    prompt=variables[final_prompt_var],
                    stop=stop,
                    best_of=num_outputs * num_candidates,
                    n=num_outputs,
                )

                # choose the first completion that isn't empty
                text_output = []
                for choice in r["choices"]:
                    text = choice["text"].strip()
                    if text:
                        text_output.append(text)
                variables[output_var] = text_output

    outputs = {}

    for output_step in doc["output_steps"]:
        match output_step["name"]:
            case "raw_text_output":
                var_name = output_step["var_name"]
                outputs[var_name] = variables[var_name]

    return {"outputs": outputs}
