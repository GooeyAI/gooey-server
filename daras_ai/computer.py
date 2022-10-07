import ast
import parse
import streamlit as st
from glom import glom
from html2text import html2text

from daras_ai.core import daras_ai_step_config
from daras_ai.train_data_formatter import input_spec_parse_pattern
import json
import json
import random

import openai
from decouple import config


def run_compute_steps(compute_steps, variables):
    for compute_step in compute_steps:
        match compute_step["name"]:
            case "text_train_data":
                training_data_json = compute_step["training_data"]

                if not training_data_json:
                    raise ValueError

                variables[compute_step["out_var"]] = json.loads(training_data_json)

            case "language_model_prompt_gen":
                prompt_header = compute_step["prompt_header"]
                completion_prefix = compute_step["completion_prefix"]
                training_data_var = compute_step["training_data_var"]
                num_prompts = compute_step["num_prompts"]
                prompt_sep = compute_step["prompt_sep"]
                completion_sep = compute_step["completion_sep"]
                final_prompt_out_var = compute_step["final_prompt_out_var"]
                prompt_input_var = compute_step["prompt_input_var"]

                prompt_input = variables.get(prompt_input_var)

                if not (training_data_var and final_prompt_out_var and prompt_input):
                    raise ValueError

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

                variables[final_prompt_out_var] = final_prompt

            case "language_model":
                api_provider = compute_step["api_provider#1"]
                selected_engine = compute_step["selected_engine#1"]
                max_tokens = compute_step["max_tokens"]
                prompt_input_var = compute_step["prompt_input_var"]
                stop = json.loads(compute_step["stop"])
                num_outputs = compute_step["num_outputs"]
                num_candidates = compute_step["num_candidates"]
                output_var = compute_step["output_var"]

                prompt = variables.get(prompt_input_var)

                if not (api_provider and prompt and output_var):
                    raise ValueError

                match api_provider:
                    case "openai":
                        openai.api_key = config("OPENAI_API_KEY")
                        openai.api_base = "https://api.openai.com/v1"
                    case "goose.ai":
                        openai.api_key = config("GOOSEAI_API_KEY")
                        openai.api_base = "https://api.goose.ai/v1"

                r = openai.Completion.create(
                    engine=selected_engine,
                    max_tokens=max_tokens,
                    prompt=prompt,
                    stop=stop,
                    best_of=num_candidates,
                    n=num_outputs,
                )

                # choose the first completion that isn't empty
                text_output = []
                for choice in r["choices"]:
                    text = choice["text"].strip()
                    if text:
                        text_output.append(text)
                variables[output_var] = text_output

            case "text_format":
                format_str = compute_step["format_str"]
                output_var = compute_step["output_var"]

                input_spec_results: list[parse.Result] = list(
                    parse.findall(input_spec_parse_pattern, format_str)
                )
                for spec_result in input_spec_results:
                    spec = spec_result.fixed[0]
                    variable_value = glom(variables, ast.literal_eval(spec))
                    format_str = format_str.replace("{{" + spec + "}}", variable_value)

                variables[output_var] = format_str
