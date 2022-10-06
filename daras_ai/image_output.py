import streamlit as st

from daras_ai.core import daras_ai_step


@daras_ai_step("Image Output", is_output=True, is_expanded=True)
def image_output(idx, variables, state):
    var_name = st.text_input(
        "", value=state.get("var_name", "image_output"), help=f"Image Output name {idx}"
    )
    state.update({"var_name": var_name})

    if var_name not in variables:
        variables[var_name] = ""

    if variables[var_name]:
        st.image(variables[var_name], caption=f"Image Output {idx + 1}")
