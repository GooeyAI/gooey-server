import ast
import parse
import streamlit as st
from glom import glom
from html2text import html2text

from daras_ai.core import daras_ai_step_config
from daras_ai.train_data_formatter import input_spec_parse_pattern


@daras_ai_step_config("Text formatter")
def text_format(idx, variables, state):
    format_str = st.text_area(
        "Format String", help=f"Format String {idx}", value=state.get("format_str", "")
    )
    state.update({"format_str": format_str})

    output_var = st.text_input(
        "Output variable",
        help=f"Output ID {idx}",
        value=state.get("output_var", ""),
    )
    state.update({"output_var": output_var})

    st.text_area(
        "Output value (generated)", value=variables.get(output_var, ""), disabled=True
    )
