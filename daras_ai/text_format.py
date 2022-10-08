import ast
import parse
import streamlit as st
from glom import glom
from html2text import html2text

from daras_ai.core import daras_ai_step_config, daras_ai_step_computer
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

    do_html2text = st.checkbox(
        "HTML -> Text",
        value=state.get("do_html2text", False),
    )
    state.update({"do_html2text": do_html2text})

    st.text_area(
        "Output value (generated)", value=variables.get(output_var, ""), disabled=True
    )


@daras_ai_step_computer
def text_format(idx, variables, state):
    format_str = state["format_str"]
    output_var = state["output_var"]
    do_html2text = state["do_html2text"]

    if not output_var:
        raise ValueError

    variables[output_var] = daras_ai_format_str(format_str, variables, do_html2text)


def daras_ai_format_str(format_str, variables, do_html2text=False):
    input_spec_results: list[parse.Result] = list(
        parse.findall(input_spec_parse_pattern, format_str)
    )
    for spec_result in input_spec_results:
        spec = spec_result.fixed[0]
        variable_value = glom(variables, ast.literal_eval(spec))
        variable_value = str(variable_value)
        if do_html2text:
            variable_value = html2text(variable_value)
        variable_value = variable_value.strip()
        format_str = format_str.replace("{{" + spec + "}}", str(variable_value))
    return format_str
