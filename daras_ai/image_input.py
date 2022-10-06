from daras_ai.core import daras_ai_step
import streamlit as st


@daras_ai_step("Image input")
def image_input(idx, variables, state):
    var_name = st.text_input(
        "", value=state.get("var_name", "image_input"), help=f"Image name {idx}"
    )
    state.update({"var_name": var_name})

    if var_name not in variables:
        variables[var_name] = None

    uploaded_file = st.file_uploader("Image input")

    variables[var_name] = uploaded_file.getvalue()
