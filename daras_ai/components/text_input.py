import streamlit as st

from daras_ai.components.core import daras_ai_step


@daras_ai_step()
def raw_text_input(variables, state, set_state):
    text_input = st.text_area("Text Input", value=state.get("text_input", ""))
    set_state({"text_input": text_input})
    variables["text_input"] = text_input
