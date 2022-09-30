import streamlit as st

from daras_ai.components.core import daras_ai_step


@daras_ai_step()
def raw_text_output(variables, state, set_state):
    st.text_area("Text Output", value=variables.get("text_output", ""))
