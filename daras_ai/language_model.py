import json

import json

import openai
import streamlit as st
from decouple import config

from daras_ai.core import daras_ai_step_computer
from daras_ai.core import daras_ai_step_config
from daras_ai_v2 import settings


@daras_ai_step_config("Language Model")
def language_model(idx, variables, state):
    st.write("#### Config")

    # select text api
    api_provider_options = ["openai", "goose.ai"]
    api_provider = st.selectbox(
        label="API provider",
        options=api_provider_options,
        index=api_provider_options.index(state.get("api_provider#1", "openai")),
    )
    state.update({"api_provider#1": api_provider})

    # set api key
    match api_provider:
        case "openai":
            # openai.api_key = config("OPENAI_API_KEY")
            # openai.api_base = "https://api.openai.com/v1"
            engine_choices = [
                "text-davinci-002",
                "text-curie-001",
                "text-babbage-001",
                "text-ada-001",
            ]
        case "goose.ai":
            # openai.api_key = config("GOOSEAI_API_KEY")
            # openai.api_base = "https://api.goose.ai/v1"
            engine_choices = [
                "gpt-neo-20b",
                "cassandra-lit-2-7b",
                "cassandra-lit-e2-2-7b",
                "cassandra-lit-e3-2-7b",
                "cassandra-lit-6-7b",
                "cassandra-lit-e2-6-7b",
                "cassandra-lit-e3-6-7b",
                "convo-6b",
                "fairseq-125m",
                "fairseq-355m",
                "fairseq-1-3b",
                "fairseq-2-7b",
                "fairseq-6-7b",
                "fairseq-13b",
                "gpt-j-6b",
                "gpt-neo-125m",
                "gpt-neo-1-3b",
                "gpt-neo-2-7b",
            ]
        case _:
            raise ValueError()

    selected_engine = st.selectbox(
        label="Engine",
        options=engine_choices,
        index=engine_choices.index(state.get("selected_engine#1", engine_choices[0])),
    )
    state.update({"selected_engine#1": selected_engine})

    num_candidates = int(
        st.number_input(
            "# of Candidate completions", value=state.get("num_candidates", 6)
        )
    )
    state.update({"num_candidates": num_candidates})

    num_outputs = int(
        st.number_input("# Of outputs to generate", value=state.get("num_outputs", 3))
    )
    state.update({"num_outputs": num_outputs})

    max_tokens = int(
        st.number_input("Max output tokens", value=state.get("max_tokens", 256))
    )
    state.update({"max_tokens": max_tokens})

    stop = json.loads(
        st.text_input("Stop sequences (JSON)", value=state.get("stop", "null"))
    )
    state.update({"stop": json.dumps(stop)})

    st.write("### Input")

    prompt_input_var = st.text_input(
        "Prompt Input Variable",
        help=f"Prompt Input Variable for language model {idx + 1}",
        value=state.get("prompt_input_var", ""),
    )
    state.update({"prompt_input_var": prompt_input_var})

    st.write("### Output")

    output_var = st.text_input(
        "Model Output Variable",
        value=state.get("output_var", ""),
    )
    state.update({"output_var": output_var})

    st.write("Model Output (generated value)")
    st.write(variables.get(output_var, ""))


@daras_ai_step_computer
def language_model(idx, variables, state):
    api_provider = state["api_provider#1"]
    selected_engine = state["selected_engine#1"]
    max_tokens = state["max_tokens"]
    prompt_input_var = state["prompt_input_var"]
    stop = json.loads(state["stop"])
    num_outputs = state["num_outputs"]
    num_candidates = state["num_candidates"]
    output_var = state["output_var"]

    prompt = variables.get(prompt_input_var)

    if not (api_provider and prompt and output_var):
        raise ValueError

    match api_provider:
        case "openai":
            openai.api_key = settings.OPENAI_API_KEY
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
