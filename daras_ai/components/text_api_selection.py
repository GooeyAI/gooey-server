import ast
import json

import openai
import parse
import streamlit as st
from decouple import config
from glom import glom
from html2text import html2text

from daras_ai.components.core import daras_ai_step
from daras_ai.components.core import daras_ai_step


@daras_ai_step("Language Model")
def language_model(variables, state, set_state):
    # select text api
    api_provider_options = ["openai", "goose.ai"]
    api_provider = st.selectbox(
        label="API provider",
        options=api_provider_options,
        index=api_provider_options.index(state.get("api_provider#1", "openai")),
    )
    set_state({"api_provider#1": api_provider})

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
    set_state({"selected_engine#1": selected_engine})

    best_of = int(st.number_input("Best of", value=state.get("best_of", 0)))
    set_state({"best_of": best_of})

    max_tokens = int(
        st.number_input("Max output tokens", value=state.get("max_tokens", 0))
    )
    set_state({"max_tokens": max_tokens})

    stop = st.text_input("Stop sequences (JSON)", value=state.get("stop", "[]"))
    set_state({"stop": stop})

    final_prompt_var = st.text_input(
        "Final prompt input var", value=state.get("final_prompt_var", "")
    )
    set_state({"final_prompt_var": final_prompt_var})

    with st.spinner():
        r = openai.Completion.create(
            engine=selected_engine,
            max_tokens=max_tokens,
            prompt=variables[final_prompt_var],
            stop=json.loads(stop),
            best_of=best_of,
        )

    # choose the first completion that isn't empty
    text_output = ""
    finish_reason = ""
    for choice in r["choices"]:
        text = choice["text"].strip()
        if text:
            text_output = text
            finish_reason = choice["finish_reason"]
            break

    st.write(f"Finish reason: {finish_reason}")
    variables["text_output"] = text_output
