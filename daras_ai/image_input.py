import streamlit as st

from daras_ai.core import daras_ai_step_config, daras_ai_step_io


@daras_ai_step_config("Image input", is_input=True)
def image_input(idx, variables, state):
    var_name = st.text_input(
        "", value=state.get("var_name", "image_input"), help=f"Image name {idx}"
    )
    state.update({"var_name": var_name})


@daras_ai_step_io
def image_input(idx, variables, state):
    var_name = state.get("var_name", "")
    if not var_name:
        return
    if var_name not in variables:
        variables[var_name] = None
    uploaded_file = st.file_uploader(var_name, help=f"Image input {var_name} {idx + 1}")
    if not uploaded_file:
        return
    variables[var_name] = uploaded_file.getvalue()

    st.image(uploaded_file.getvalue(), width=300)
