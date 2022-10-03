import streamlit as st

from daras_ai.components.core import daras_ai_step


@daras_ai_step("Text Input", is_input=True, is_expanded=True)
def raw_text_input(idx, variables, state):
    var_name = st.text_input(
        "", value=state.get("var_name", "text_input"), help=f"Input name {idx}"
    )
    state.update({"var_name": var_name})

    if var_name not in variables:
        variables[var_name] = ""

    value = st.text_area("", value=variables[var_name], help=f"Input value {idx}")
    variables[var_name] = value
