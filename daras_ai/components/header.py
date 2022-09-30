import ast

import parse
import streamlit as st
from glom import glom
from html2text import html2text

from daras_ai.components.core import daras_ai_step


@daras_ai_step()
def header(variables, state, set_state):
    title = st.text_input("Title", value=state.get("title", ""))
    set_state({"title": title})

    description = st.text_area("Description", value=state.get("description", ""))
    set_state({"description": description})
