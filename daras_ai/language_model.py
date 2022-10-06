import json

import openai
import streamlit as st
from decouple import config

from daras_ai.core import var_selector
from daras_ai.core import daras_ai_step


@daras_ai_step("Language Model")
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
            openai.api_key = config("OPENAI_API_KEY")
            openai.api_base = "https://api.openai.com/v1"
            engine_choices = [
                "text-davinci-002",
                "text-curie-001",
                "text-babbage-001",
                "text-ada-001",
            ]
        case "goose.ai":
            openai.api_key = config("GOOSEAI_API_KEY")
            openai.api_base = "https://api.goose.ai/v1"
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
        st.number_input("Max output tokens", value=state.get("max_tokens", 128))
    )
    state.update({"max_tokens": max_tokens})

    stop = json.loads(
        st.text_input("Stop sequences (JSON)", value=state.get("stop", "null"))
    )
    state.update({"stop": json.dumps(stop)})

    st.write("#### I/O")

    final_prompt_var = var_selector(
        "Final prompt input var",
        state=state,
        variables=variables,
    )
    output_var = var_selector(
        "Model output var",
        state=state,
        variables=variables,
    )

    if not (final_prompt_var and output_var):
        return

    with st.spinner():
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
    # finish_reason = ""
    for choice in r["choices"]:
        text = choice["text"].strip()
        if text:
            text_output.append(text)
            # finish_reason = choice["finish_reason"]

    # st.write(f"Finish reason: {finish_reason}")
    variables[output_var] = text_output
