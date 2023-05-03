import streamlit2 as st

from daras_ai.core import daras_ai_step_config, daras_ai_step_computer
from daras_ai.nsp_pantry import nsp_parse


@daras_ai_step_config("Noodle Soup Prompts")
def noodle_soup_prompts(idx, variables, state):
    st.write("### Input")

    prompt_input_var = st.text_input(
        "Input Variable",
        help=f"Prompt Input Variable for NSP {idx + 1}",
        value=state.get("prompt_input_var", ""),
    )
    state.update({"prompt_input_var": prompt_input_var})

    st.write("### Output")

    output_var = st.text_input(
        "Output Variable",
        value=state.get("output_var", ""),
        help=f"Prompt Output Variable for NSP {idx + 1}",
    )
    state.update({"output_var": output_var})


@daras_ai_step_computer
def noodle_soup_prompts(idx, variables, state):
    prompt_input_var = state["prompt_input_var"]
    prompt = variables.get(prompt_input_var)
    output_var = state["output_var"]

    if not (prompt and output_var):
        raise ValueError

    variables[output_var] = nsp_parse(prompt)
