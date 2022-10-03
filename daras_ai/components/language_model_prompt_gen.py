import ast
import random

import openai
import parse
import streamlit as st
from decouple import config
from glom import glom
from html2text import html2text

from daras_ai.components.core import daras_ai_step
from daras_ai.components.core import daras_ai_step


@daras_ai_step("Language Model Prompt Generator")
def language_model_prompt_gen(idx, variables, state):
    st.write("### Config")

    prompt_header = st.text_area(
        label="Prompt header",
        value=state.get("prompt_header", ""),
    )
    state.update({"prompt_header": prompt_header})

    prompt_sep = st.text_area(
        "Prompt end separator", value=state.get("prompt_sep", "\n$$$$\n")
    )
    state.update({"prompt_sep": prompt_sep})

    completion_prefix = st.text_area(
        "Completion prefix", value=state.get("completion_prefix", "Response: ")
    )
    state.update({"completion_prefix": completion_prefix})

    completion_prefix = completion_prefix.strip() + " "
    completion_sep = st.text_area(
        "Completion end separator", value=state.get("completion_sep", "\n####\n")
    )
    state.update({"completion_sep": completion_sep})

    num_prompts = int(
        st.number_input("Number of examples", value=state.get("num_prompts", 1))
    )
    state.update({"num_prompts": num_prompts})

    st.write("### Generation")

    training_data_var = st.text_input(
        "Training data var", value=state.get("training_data_var", "")
    )
    state.update({"training_data_var": training_data_var})

    final_prompt = prompt_header.strip() + "\n\n"
    for eg in random.choices(variables[training_data_var], k=num_prompts):
        final_prompt += (
            eg["prompt"]
            + prompt_sep
            + completion_prefix
            + eg["completion"]
            + completion_sep
        )

    final_prompt += variables["text_input"] + prompt_sep + completion_prefix

    st.text_area("", value=final_prompt)

    final_prompt_var = st.text_input(
        "Final prompt out var", value=state.get("final_prompt_var", "")
    )
    state.update({"final_prompt_var": final_prompt_var})
    variables[final_prompt_var] = final_prompt
