import streamlit as st

from daras_ai.core import daras_ai_step_config, daras_ai_step_io


@daras_ai_step_config("Text Input", is_input=True, is_expanded=True)
def text_input(idx, variables, state):
    var_name = st.text_input(
        "Variable Name",
        value=state.get("var_name", "text_input"),
        help=f"Input name {idx}",
    )
    state.update({"var_name": var_name})


@daras_ai_step_io
def text_input(idx, variables, state):
    var_name = state.get("var_name", "")
    if not var_name:
        return
    if var_name not in variables:
        variables[var_name] = ""
    value = st.text_area(var_name, value=variables[var_name], help=f"Input value {idx}")
    variables[var_name] = value
