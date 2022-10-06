import streamlit as st

from daras_ai.core import daras_ai_step


@daras_ai_step("Text Output", is_output=True, is_expanded=True)
def raw_text_output(idx, variables, state):
    var_name = st.text_input(
        "", value=state.get("var_name", "text_output"), help=f"Text Output name {idx}"
    )
    state.update({"var_name": var_name})

    if var_name not in variables:
        variables[var_name] = ""

    text_list = variables[var_name]
    if not isinstance(text_list, list):
        text_list = [text_list]

    for j, text in enumerate(text_list):
        st.text_area(
            "",
            help=f"Output value {idx + 1}, {j + 1}",
            value=text,
        )
