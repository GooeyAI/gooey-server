import random

import streamlit as st

from daras_ai.core import daras_ai_step
from daras_ai.core import var_selector
from daras_ai.train_data_formatter import format_input_var


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

    completion_sep = st.text_area(
        "Completion end separator", value=state.get("completion_sep", "\n####\n")
    )
    state.update({"completion_sep": completion_sep})

    num_prompts = int(
        st.number_input("Number of examples", value=state.get("num_prompts", 1))
    )
    state.update({"num_prompts": num_prompts})

    st.write("### Input")

    training_data_var = var_selector(
        "Training data input var",
        state=state,
        variables=variables,
    )

    prompt_input_var = st.text_area(
        "Prompt input",
        value=state.get("prompt_input_var", ""),
    )
    state.update({"prompt_input_var": prompt_input_var})

    final_prompt_var = var_selector(
        "Final prompt out var",
        state=state,
        variables=variables,
    )

    if not (training_data_var and final_prompt_var and prompt_input_var):
        return

    prompt_input = format_input_var(prompt_input_var, variables)

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

    st.write("### Output")

    st.text_area("Final prompt (generated)", value=final_prompt)
