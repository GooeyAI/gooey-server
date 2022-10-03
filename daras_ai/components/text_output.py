import streamlit as st

from daras_ai.components.core import daras_ai_step


@daras_ai_step("Text Output", is_output=True, is_expanded=True)
def raw_text_output(idx, variables, state):
    var_name = st.text_input(
        "", value=state.get("var_name", "text_output"), help=f"Output name {idx}"
    )
    state.update({"var_name": var_name})

    if var_name not in variables:
        variables[var_name] = ""

    st.text_area("", value=variables[var_name], help=f"Output value {idx}")
