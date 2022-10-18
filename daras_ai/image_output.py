from math import ceil

import streamlit as st

from daras_ai.core import daras_ai_step_config, daras_ai_step_io


@daras_ai_step_config("Image Output", is_output=True, is_expanded=True)
def image_output(idx, variables, state):
    var_name = st.text_input(
        "Variable Name",
        value=state.get("var_name", "image_output"),
        help=f"Image Output name {idx}",
    )
    state.update({"var_name": var_name})


@daras_ai_step_io
def image_output(idx, variables, state):
    var_name = state.get("var_name", "")
    if not var_name:
        return
    if var_name not in variables:
        variables[var_name] = []

    images = variables[var_name]
    if not images:
        return
    if not isinstance(images, list):
        images = [images]

    st.write(f"{var_name}")

    col1, col2 = st.columns(2)

    images = [img for img in images if img]
    mid = ceil(len(images) / 2)
    col1_images = images[:mid]
    if col1_images:
        with col1:
            st.image(col1_images)
    col2_images = images[mid:]
    if col2_images:
        with col2:
            st.image(col2_images)
