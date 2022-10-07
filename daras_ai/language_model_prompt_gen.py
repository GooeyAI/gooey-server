import random

import streamlit as st

from daras_ai.core import daras_ai_step_config
from daras_ai.core import var_selector


@daras_ai_step_config("Training Data -> Prompt")
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

    training_data_var = st.text_input(
        "Training Data Input Variable",
        value=state.get("training_data_var", ""),
    )
    state.update({"training_data_var": training_data_var})

    prompt_input_var = st.text_input(
        "Prompt Input Variable",
        value=state.get("prompt_input_var", ""),
    )
    state.update({"prompt_input_var": prompt_input_var})

    st.write("### Output")

    final_prompt_out_var = st.text_input(
        "Final Prompt Output Variable",
        value=state.get("final_prompt_out_var", ""),
    )
    state.update({"final_prompt_out_var": final_prompt_out_var})

    st.text_area(
        "Final prompt (generated value)",
        value=variables.get(final_prompt_out_var, ""),
        disabled=True,
    )
